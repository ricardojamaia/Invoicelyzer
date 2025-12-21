from imap_tools.mailbox import MailBox
from imap_tools.query import AND
from pathlib import Path
import logging
import time
from typing import List, Dict, Callable, Optional
import re

logger = logging.getLogger("invoice_processor.email_monitor")


class EmailMonitor:
    """
    Monitor email inbox for invoice PDFs.
    """
    
    def __init__(
        self,
        imap_server: str,
        email: str,
        password: str,
        sender_config: Dict[str, List[str]],
        pdf_storage_dir: str = "./invoices"
    ):
        """
        Args:
            imap_server: IMAP server address (e.g., imap.gmail.com)
            email: Email address
            password: Email password or app password
            sender_config: Dictionary mapping folder names to list of sender emails
                          e.g., {"store1": ["noreply@store1.com", "info@store1.com"]}
            pdf_storage_dir: Directory to store PDF invoices (organized by folder name)
        """
        self.imap_server = imap_server
        self.email = email
        self.password = password
        self.sender_config = sender_config
        self.pdf_storage_dir = Path(pdf_storage_dir)
        
        # Build reverse mapping: email -> folder_name
        self.email_to_folder = {}
        for folder_name, email_list in sender_config.items():
            for sender_email in email_list:
                self.email_to_folder[sender_email.lower()] = folder_name
        
        # Get flat list of all allowed senders
        self.allowed_senders = [email.lower() for emails in sender_config.values() for email in emails]
        
        # Create base directory
        self.pdf_storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized EmailMonitor for {email}")
        logger.info(f"Monitoring {len(self.allowed_senders)} sender addresses across {len(sender_config)} folders")
        for folder_name, emails in sender_config.items():
            logger.debug(f"  {folder_name}: {len(emails)} senders")
    
    def _get_folder_name_from_sender(self, sender: str) -> str:
        """
        Get folder name for a sender email address.
        
        Args:
            sender: Email sender address
            
        Returns:
            Folder name from configuration
        """
        sender_lower = sender.lower()
        
        # Look up in mapping
        if sender_lower in self.email_to_folder:
            folder_name = self.email_to_folder[sender_lower]
            logger.debug(f"Mapped sender '{sender}' to folder '{folder_name}'")
            return folder_name
        
        # Fallback: sanitize sender email as folder name
        safe_sender = re.sub(r'[^\w\-]', '_', sender_lower)
        logger.warning(f"Sender '{sender}' not in configuration, using '{safe_sender}' as folder")
        return safe_sender
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for safe storage.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove or replace problematic characters
        filename = filename.replace('/', '-')
        filename = filename.replace('\\', '-')
        filename = filename.replace(':', '-')
        filename = filename.replace('*', '-')
        filename = filename.replace('?', '-')
        filename = filename.replace('"', '-')
        filename = filename.replace('<', '-')
        filename = filename.replace('>', '-')
        filename = filename.replace('|', '-')
        
        # Remove any other non-alphanumeric characters except . - _
        filename = re.sub(r'[^\w\-.]', '_', filename)
        
        return filename
    
    def check_new_invoices(
        self,
        process_callback: Callable[[str, str], bool],
        mark_as_read: bool = True,
        folder: str = "INBOX"
    ) -> int:
        """
        Check for new invoice emails and process them.
        
        Args:
            process_callback: Function to call for each PDF (pdf_path, sender) -> success
            mark_as_read: Mark emails as read after processing
            folder: Email folder to monitor
            
        Returns:
            Number of invoices processed
        """
        logger.info(f"Checking for new invoices in {folder}")
        processed_count = 0
        
        try:
            with MailBox(self.imap_server).login(self.email, self.password, initial_folder=folder) as mailbox:
                # Search for unread emails from allowed senders
                for sender in self.allowed_senders:
                    logger.debug(f"Searching emails from: {sender}")
                    
                    # Get unread messages from this sender
                    messages = mailbox.fetch(
                        AND(from_=sender, seen=False),
                        mark_seen=False
                    )
                    
                    for msg in messages:
                        logger.info(f"Processing email: {msg.subject} from {msg.from_}")
                        
                        # Determine folder name from configuration
                        folder_name = self._get_folder_name_from_sender(msg.from_)
                        sender_dir = self.pdf_storage_dir / folder_name
                        sender_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Process each PDF attachment
                        for att in msg.attachments:
                            if att.filename.lower().endswith('.pdf'):
                                logger.info(f"Found PDF attachment: {att.filename}")
                                
                                # Keep original filename, sanitized
                                safe_filename = self._sanitize_filename(att.filename)
                                pdf_path = sender_dir / safe_filename
                                
                                # Check if file already exists
                                if pdf_path.exists():
                                    logger.info(f"PDF already exists, using existing file: {pdf_path}")
                                    # Don't save again, just process the existing file
                                else:
                                    # Save PDF to permanent location
                                    try:
                                        with open(pdf_path, 'wb') as f:
                                            f.write(att.payload)
                                        logger.info(f"Saved new PDF to: {pdf_path}")
                                    except Exception as e:
                                        logger.error(f"Failed to save PDF {att.filename}: {str(e)}", exc_info=True)
                                        continue
                                
                                try:
                                    # Process the PDF (existing or new)
                                    success = process_callback(str(pdf_path), msg.from_)
                                    
                                    if success:
                                        processed_count += 1
                                        logger.info(f"Successfully processed invoice from {msg.from_}")
                                        
                                        # Mark as read if configured
                                        if mark_as_read and msg.uid:
                                            mailbox.flag([msg.uid], ['\\Seen'], True)
                                            logger.debug(f"Marked email as read: {msg.uid}")
                                    else:
                                        logger.warning(f"Failed to process invoice from {msg.from_}")
                                    
                                except Exception as e:
                                    logger.error(f"Error processing attachment {att.filename}: {str(e)}", exc_info=True)
                
                logger.info(f"Processed {processed_count} invoices")
                return processed_count
                
        except Exception as e:
            logger.error(f"Error checking emails: {str(e)}", exc_info=True)
            raise Exception(f"Email check failed: {str(e)}")
    
    def monitor_continuous(
        self,
        process_callback: Callable[[str, str], bool],
        check_interval: int = 300,
        mark_as_read: bool = True,
        folder: str = "INBOX"
    ):
        """
        Continuously monitor inbox for new invoices.
        
        Args:
            process_callback: Function to call for each PDF
            check_interval: Seconds between checks (default: 300 = 5 minutes)
            mark_as_read: Mark emails as read after processing
            folder: Email folder to monitor
        """
        logger.info(f"Starting continuous monitoring (check every {check_interval}s)")
        
        while True:
            try:
                count = self.check_new_invoices(process_callback, mark_as_read, folder)
                
                if count > 0:
                    logger.info(f"Processed {count} invoices, waiting {check_interval}s for next check")
                else:
                    logger.debug(f"No new invoices, waiting {check_interval}s for next check")
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}", exc_info=True)
                logger.info(f"Waiting {check_interval}s before retry")
                time.sleep(check_interval)

                
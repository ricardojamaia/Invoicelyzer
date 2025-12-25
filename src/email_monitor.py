"""
Email monitoring - responsible for checking emails and downloading PDF attachments.
"""
import logging
import time
from typing import Callable, Optional
from pathlib import Path
import imaplib
from imap_tools.mailbox import MailBox
from imap_tools.query import AND

logger = logging.getLogger("invoice_processor.email_monitor")


class EmailMonitor:
    """Monitors email for invoice attachments."""
    
    def __init__(
        self,
        imap_server: str,
        email: str,
        password: str,
        pdf_storage_dir: str,
        sender_filters: Optional[dict] = None
    ):
        """
        Initialize email monitor.
        
        Args:
            imap_server: IMAP server address
            email: Email address
            password: Email password
            pdf_storage_dir: Directory to save downloaded PDFs
            sender_filters: Optional dict of sender configurations
        """
        self.imap_server = imap_server
        self.email = email
        self.password = password
        self.pdf_storage_dir = Path(pdf_storage_dir)
        self.sender_filters = sender_filters or {}
        
        self.pdf_storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized EmailMonitor")
        logger.info(f"  IMAP: {imap_server}")
        logger.info(f"  Email: {email}")
        logger.info(f"  Storage: {pdf_storage_dir}")
    
    def _get_sender_folder(self, sender: str) -> Path:
        """Get storage folder for sender."""
        if sender in self.sender_filters:
            folder_name = self.sender_filters[sender].get('folder', sender)
        else:
            if '@' in sender:
                folder_name = sender.split('@')[1].replace('.', '_')
            else:
                folder_name = 'unknown'
        
        folder = self.pdf_storage_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    
    def _download_pdf(self, attachment, sender: str) -> str:
        """Save PDF attachment to disk."""
        folder = self._get_sender_folder(sender)
        filename = attachment.filename
        filepath = folder / filename
        
        if filepath.exists():
            logger.info(f"PDF already exists: {filepath}")
            return str(filepath)
        
        with open(filepath, 'wb') as f:
            f.write(attachment.payload)
        
        logger.info(f"Saved PDF: {filepath}")
        return str(filepath)
    
    def check_new_emails(
        self,
        process_callback: Callable[[str, str], bool],
        mark_as_read: bool = True
    ) -> int:
        """
        Check for new emails with PDF attachments.
        
        Args:
            process_callback: Function(pdf_path, sender) -> bool
                             Returns True to mark as read, False to keep unread
            mark_as_read: Whether to mark emails as read
            
        Returns:
            Number of emails processed
        """
        logger.info("Checking for new invoice emails...")
        
        processed_count = 0
        
        try:
            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                messages = list(mailbox.fetch(AND(seen=False)))
                
                if not messages:
                    logger.info("No new emails")
                    return 0
                
                logger.info(f"Found {len(messages)} unread emails")
                
                for msg in messages:
                    sender = msg.from_
                    subject = msg.subject
                    
                    logger.info(f"Processing email from {sender}: {subject}")
                    
                    pdf_attachments = [att for att in msg.attachments if att.filename.lower().endswith('.pdf')]
                    
                    if not pdf_attachments:
                        logger.debug(f"No PDF attachments in email from {sender}")
                        continue
                    
                    should_mark_read = True
                    
                    for attachment in pdf_attachments:
                        try:
                            pdf_path = self._download_pdf(attachment, sender)
                            logger.info(f"Calling processing callback for: {pdf_path}")
                            callback_result = process_callback(pdf_path, sender)
                            
                            if not callback_result:
                                should_mark_read = False
                                logger.info("Callback returned False - will keep email unread")
                            else:
                                logger.info("Callback returned True - will mark as read")
                            
                        except Exception as e:
                            logger.error(f"Error processing attachment: {e}", exc_info=True)
                            should_mark_read = False
                    
                    if mark_as_read and should_mark_read:
                        if msg.uid is not None:
                            mailbox.flag([msg.uid], ['\\Seen'], True)
                            logger.info(f"✓ Marked email as read")
                        else:
                            logger.warning("Cannot mark email as read: UID is None")
                    elif not should_mark_read:
                        logger.info(f"⏳ Keeping email unread (will retry)")
                    
                    processed_count += 1
                
                logger.info(f"Processed {processed_count} emails")
                return processed_count
        
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error checking emails: {e}", exc_info=True)
            raise
    
    def monitor_continuous(
        self,
        process_callback: Callable[[str, str], bool],
        check_interval: int = 300,
        mark_as_read: bool = True
    ):
        """
        Continuously monitor for new emails.
        
        Args:
            process_callback: Function(pdf_path, sender) -> bool
            check_interval: Seconds between checks
            mark_as_read: Whether to mark emails as read
        """
        logger.info("Starting continuous email monitoring")
        logger.info(f"Check interval: {check_interval}s")
        
        while True:
            try:
                count = self.check_new_emails(process_callback, mark_as_read)
                
                if count > 0:
                    logger.info(f"✓ Processed {count} emails")
                
                logger.info(f"Waiting {check_interval}s until next check...")
                time.sleep(check_interval)
            
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                logger.info(f"Retrying in {check_interval}s...")
                time.sleep(check_interval)
                
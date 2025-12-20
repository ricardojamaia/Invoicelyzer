import requests
import json
from typing import Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger("invoice_processor.analyzer")


class InvoiceAnalyzer:
    """
    Analyze and structure raw invoice text using LLM.
    """
    
    def __init__(self, llm_url: str, model: str = "llama3.2:3b", prompt_template: Optional[str] = None):
        """
        Args:
            llm_url: URL of LLM API endpoint
            model: Model name to use for analysis
            prompt_template: Path to custom prompt template file (optional)
        """
        self.llm_url = llm_url
        self.model = model
        
        # Load prompt template
        if prompt_template:
            self.prompt_template_path = Path(prompt_template)
        else:
            # Default to prompts/default.txt relative to project root
            # Assumes this file is in ./src/
            project_root = Path(__file__).parent.parent
            self.prompt_template_path = project_root / "prompts" / "default.txt"
        
        logger.info(f"Initializing InvoiceAnalyzer with URL: {llm_url}, model: {model}")
        logger.info(f"Using prompt template: {self.prompt_template_path}")
        
        self._load_prompt_template()
        self._verify_connection()
    
    def _load_prompt_template(self):
        """Load the prompt template from file."""
        try:
            with open(self.prompt_template_path, 'r', encoding='utf-8') as f:
                self.prompt_template = f.read()
            logger.debug(f"Loaded prompt template ({len(self.prompt_template)} chars)")
        except FileNotFoundError:
            logger.error(f"Prompt template not found: {self.prompt_template_path}")
            raise Exception(f"Prompt template file not found: {self.prompt_template_path}")
        except Exception as e:
            logger.error(f"Error loading prompt template: {str(e)}")
            raise
    
    def _verify_connection(self):
        """Check if LLM service is accessible."""
        logger.debug(f"Verifying LLM connection at {self.llm_url}")
        
        try:
            response = requests.get(f"{self.llm_url}/api/tags", timeout=5)
            response.raise_for_status()
            logger.info("Successfully connected to LLM service")
            
            # Log available models
            models = response.json().get('models', [])
            model_names = [m.get('name') for m in models]
            logger.debug(f"Available models: {model_names}")
            
            if self.model not in model_names:
                logger.warning(f"Configured model '{self.model}' not found in available models")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to LLM service: {str(e)}")
            raise Exception(
                f"Cannot connect to LLM service at {self.llm_url}. "
                f"Make sure the service is running. Error: {str(e)}"
            )
    
    def analyze(self, raw_text: str, context: Optional[Dict] = None) -> Dict:
        """
        Analyze raw invoice text and extract structured data.
        
        Args:
            raw_text: Raw text extracted from invoice
            context: Optional context (e.g., known store, expected date range)
            
        Returns:
            Structured invoice data as dictionary
        """
        logger.info(f"Starting invoice analysis ({len(raw_text)} chars)")
        if context:
            logger.debug(f"Using context: {context}")
        
        prompt = self._build_prompt(raw_text, context)
        logger.debug(f"Generated prompt length: {len(prompt)} chars")
        
        result = None  # Initialize to avoid unbound variable
        
        try:
            logger.debug(f"Sending request to LLM: {self.llm_url}/api/generate")
            
            request_payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 4096
                }
            }
            
            logger.debug(f"Request payload: {json.dumps({k: v if k != 'prompt' else f'<{len(v)} chars>' for k, v in request_payload.items()})}")
            
            response = requests.post(
                f"{self.llm_url}/api/generate",
                json=request_payload,
                timeout=120
            )
            
            logger.debug(f"Response status code: {response.status_code}")
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"Response JSON keys: {list(result.keys())}")
            
            # Get the response text
            response_text = result.get('response', '')
            logger.debug(f"Response text length: {len(response_text)} chars")
            
            if not response_text:
                logger.error("LLM returned empty response")
                logger.debug(f"Full result: {json.dumps(result, indent=2)}")
                raise ValueError("LLM returned empty response")
            
            logger.debug(f"Response preview (first 500 chars): {response_text[:500]}")
            
            # Try to extract JSON if the response contains extra text
            invoice_data = self._extract_json(response_text)
            logger.debug(f"Parsed JSON with {len(invoice_data)} fields: {list(invoice_data.keys())}")
            
            # Validate required fields
            self._validate_invoice_data(invoice_data)
            
            logger.info(
                f"Successfully analyzed invoice: {invoice_data.get('store', 'Unknown')} - "
                f"{len(invoice_data.get('items', []))} items - "
                f"€{invoice_data.get('total', 0)}"
            )
            
            return invoice_data
            
        except requests.exceptions.Timeout:
            logger.error("LLM request timed out after 120 seconds")
            raise Exception("LLM request timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
            raise Exception(f"Error calling LLM API: {str(e)}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing LLM response: {str(e)}", exc_info=True)
            if result:
                logger.debug(f"Full response content: {result.get('response', 'N/A')}")
            raise Exception(f"Error parsing LLM response: {str(e)}")
    
    def _extract_json(self, text: str) -> Dict:
        """
        Extract JSON from response text.
        Handles cases where LLM adds extra text before/after JSON.
        
        Args:
            text: Raw text from LLM
            
        Returns:
            Parsed JSON dictionary
        """
        logger.debug(f"Attempting to extract JSON from text length: {len(text)}")
        
        # Try direct JSON parse first
        try:
            data = json.loads(text)
            logger.debug("Successfully parsed JSON directly")
            return data
        except json.JSONDecodeError as e:
            logger.debug(f"Direct JSON parse failed: {str(e)}")
        
        # Try to find JSON object in text
        # Look for the first { and last }
        start = text.find('{')
        end = text.rfind('}')
        
        logger.debug(f"Searching for JSON boundaries: start={start}, end={end}")
        
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            logger.debug(f"Extracted JSON substring length: {len(json_str)}")
            logger.debug(f"Extracted JSON preview: {json_str[:200]}")
            try:
                data = json.loads(json_str)
                logger.debug("Successfully parsed extracted JSON")
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse extracted JSON: {str(e)}")
        
        # If all else fails, raise error
        logger.error(f"Could not extract valid JSON. Text preview: {text[:500]}")
        raise ValueError(f"Could not extract valid JSON from response")
    
    def _build_prompt(self, raw_text: str, context: Optional[Dict] = None) -> str:
        """Build the analysis prompt using the template."""
        context_hint = ""
        if context:
            context_hint = f"\nContexto adicional: {json.dumps(context, ensure_ascii=False)}\n"
        
        # Use the loaded template and format it
        prompt = self.prompt_template.format(
            context_hint=context_hint,
            raw_text=raw_text
        )
        
        return prompt
    
    def _validate_invoice_data(self, data: Dict) -> None:
        """Validate that invoice data has required structure."""
        logger.debug("Validating invoice data structure")
        
        required_fields = ["store", "date", "items", "total"]
        missing = [field for field in required_fields if field not in data]
        
        if missing:
            logger.error(f"Missing required fields: {missing}")
            raise ValueError(f"Missing required fields in invoice data: {missing}")
        
        if not isinstance(data["items"], list):
            logger.error("Items field is not a list")
            raise ValueError("Items must be a list")
        
        if len(data["items"]) == 0:
            logger.warning("No items found in invoice")
            raise ValueError("No items found in invoice")
        
        # Validate item structure
        for i, item in enumerate(data["items"]):
            required_item_fields = ["name", "quantity", "unit_price", "total_price"]
            missing_item_fields = [field for field in required_item_fields if field not in item]
            
            if missing_item_fields:
                logger.warning(f"Item {i} missing fields: {missing_item_fields}")
            
            # Category is optional
            if "category" in item:
                logger.debug(f"Item {i} ({item['name']}) has category: {item['category']}")
        
        logger.debug(f"Validation passed: {len(data['items'])} items found")
        
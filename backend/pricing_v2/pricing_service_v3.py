# In: backend/pricing_v2/pricing_service_v3.py
# (Replace the entire file with this)

import json
import logging
from dataclasses import asdict
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
from django.db import transaction

from django.utils import timezone # Add this

# Models
from core.models import FxSnapshot, Airport, Currency
from parties.models import CustomerCommercialProfile, Company, Contact # Add Contact
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal # QuoteLine & QuoteTotal
from services.models import ServiceComponent, IncotermRule # Add IncotermRule
# Import new PartnerRate models
from ratecards.models import PartnerRate
# V2 rate card service

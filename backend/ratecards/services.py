import csv
from decimal import Decimal, InvalidOperation
from django.db import transaction
from .models import RateCardLane, RateBreak, Surcharge

class RateCardParsingService:
    """
    A service to handle the parsing and storage of rate card files.
    """

    def parse_and_store(self, ratecard_file_instance):
        """
        Reads a CSV file associated with a RatecardFile instance, parses its
        contents, and populates the database with lane, break, and surcharge data.

        Args:
            ratecard_file_instance: The RatecardFile model instance to process.
        
        This assumes the CSV has the following headers:
        - origin_code
        - destination_code
        - weight_break_kg
        - rate_per_kg
        - surcharge_name (optional)
        - surcharge_code (optional)
        - surcharge_rate (optional)
        """
        # Use a transaction to ensure all-or-nothing data import
        with transaction.atomic():
            # Clear any existing data related to this file to prevent duplicates on re-upload
            ratecard_file_instance.lanes.all().delete()

            # Open the file from storage and read it
            file = ratecard_file_instance.file
            file.open(mode='r')
            try:
                # Assuming the file is UTF-8, decode it
                decoded_file = (line.decode('utf-8') for line in file)
                reader = csv.DictReader(decoded_file)
                
                for row in reader:
                    # Find or create the lane for this row
                    lane, _ = RateCardLane.objects.get_or_create(
                        ratecard_file=ratecard_file_instance,
                        origin_code=row['origin_code'],
                        destination_code=row['destination_code']
                    )

                    # Create the rate break for this lane
                    try:
                        RateBreak.objects.create(
                            lane=lane,
                            weight_break_kg=Decimal(row['weight_break_kg']),
                            rate_per_kg=Decimal(row['rate_per_kg'])
                        )
                    except (InvalidOperation, KeyError):
                        # Handle cases where rate break columns are missing or invalid
                        # You could add more robust logging or error handling here
                        continue

                    # If surcharge information exists, create the surcharge
                    if row.get('surcharge_name') and row.get('surcharge_code') and row.get('surcharge_rate'):
                        try:
                            Surcharge.objects.create(
                                lane=lane,
                                name=row['surcharge_name'],
                                code=row['surcharge_code'],
                                rate=Decimal(row['surcharge_rate'])
                            )
                        except InvalidOperation:
                            # Handle invalid surcharge rate
                            continue
            finally:
                file.close()
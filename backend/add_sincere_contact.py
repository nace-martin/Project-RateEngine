import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.models import Country, City
from parties.models import Company, Contact, Address

def add_agent():
    print("Starting agent addition...")

    # 1. Ensure Country exists
    country, created = Country.objects.get_or_create(code='CN', defaults={'name': 'China'})
    if created:
        print(f"Created Country: {country}")
    else:
        print(f"Found Country: {country}")

    # 2. Ensure City exists
    city, created = City.objects.get_or_create(
        name='Shenzhen', 
        country=country,
    )
    if created:
        print(f"Created City: {city}")
    else:
        print(f"Found City: {city}")

    # 3. Create/Get Company
    company_name = "Sincere International Logistics Co. Ltd"
    company, created = Company.objects.get_or_create(
        name=company_name,
        defaults={'company_type': 'SUPPLIER'} # Assuming supplier/agent for now, or could be CUSTOMER
    )
    if created:
        print(f"Created Company: {company}")
    else:
        print(f"Found Company: {company}")

    # 4. Create Contact
    contact_email = "wade@sincere-logistics.com"
    contact, created = Contact.objects.get_or_create(
        email=contact_email,
        defaults={
            'company': company,
            'first_name': 'Wade',
            'last_name': 'Lee',
            'is_primary': True
        }
    )
    if created:
        print(f"Created Contact: {contact}")
    else:
        # Update existing contact if needed? For now just report.
        print(f"Found Contact: {contact}")
        if contact.company != company:
             print(f"WARNING: Contact {contact_email} exists but belongs to {contact.company}, not {company_name}")


    # 5. Create Address
    address_line_1 = "Rm 623,Investment Building,No.4044 Pingshan Avenue"
    address_line_2 = "Pingshan District"
    
    # Check if address already exists to avoid duplicates (loose check)
    address_exists = Address.objects.filter(
        company=company,
        address_line_1=address_line_1,
        city=city
    ).exists()

    if not address_exists:
        address = Address.objects.create(
            company=company,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            country=country,
            is_primary=True
        )
        print(f"Created Address: {address}")
    else:
        print("Address already exists.")

    print("Agent addition complete.")

if __name__ == '__main__':
    add_agent()

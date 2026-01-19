
import os
import django
import sys

# Add the project directory to the path
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from parties.models import Company, Contact

def list_companies_and_contacts():
    companies = Company.objects.all()
    print(f"Found {companies.count()} companies.")
    for company in companies:
        contacts = company.contacts.all()
        print(f"Company: {company.name} ({company.id}) - Is Customer: {company.is_customer}")
        print(f"  Contacts ({contacts.count()}):")
        for contact in contacts:
            print(f"    - {contact.first_name} {contact.last_name} ({contact.id})")
        print("-" * 20)

if __name__ == "__main__":
    list_companies_and_contacts()

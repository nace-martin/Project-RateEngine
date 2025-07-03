# Python script to populate Firestore with local airfreight fees.

# Instructions for running this script:
# 1. Ensure you have the google-cloud-firestore library installed:
#    pip install google-cloud-firestore
# 2. Set up Google Cloud authentication.
#    - If running locally, you can use the Google Cloud CLI:
#      gcloud auth application-default login
#    - If running in a Google Cloud environment (e.g., Cloud Functions, App Engine),
#      authentication should be handled automatically.
# 3. Make sure your Firestore database is initialized and you have write permissions.
# 4. Run the script:
#    python populate_firestore.py

# Data to be populated into Firestore
LOCAL_CHARGES_DATA = {
    "agencyFee": {
        "feeName": "Agency Fee",
        "type": "flat",
        "amount": 250,
        "gstApplicable": True,
        "appliesTo": ["import", "export"]
    },
    "customsClearance": {
        "feeName": "Customs Clearance",
        "type": "flat",
        "amount": 300,
        "gstApplicable": True,
        "appliesTo": ["import", "export"]
    },
    "documentationFee": {
        "feeName": "Documentation Fee",
        "type": "flat",
        "amount": 165,
        "gstApplicable": True,
        "appliesTo": ["import"]
    },
    "handlingFee": {
        "feeName": "Handling Fee - General Cargo",
        "type": "flat",
        "amount": 165,
        "gstApplicable": True,
        "appliesTo": ["import"]
    },
    "cartage": {
        "feeName": "Cartage & Delivery",
        "type": "perKgWithMinAndCap",
        "rate": 1.5,
        "minCharge": 95,
        "maxCharge": 500,
        "gstApplicable": True,
        "appliesTo": ["import", "export"]
    },
    "fuelSurcharge": {
        "feeName": "Fuel Surcharge",
        "type": "percentOf",
        "percent": 10,
        "appliesTo": ["cartage"],
        "gstApplicable": True
    },
    "dgFee": {
        "feeName": "DG Documentation & Handling Fee",
        "type": "conditionalFlat",
        "amount": 250,
        "gstApplicable": True,
        "condition": "isDG"
    },
    "oohSurcharge": {
        "feeName": "Out-of-Hours Surcharge",
        "type": "conditionalPercentOf",
        "percent": 20,
        "appliesTo": ["cartage", "handlingFee"],
        "condition": "isAfterHours",
        "gstApplicable": True
    }
}

# Import the Firestore library
from google.cloud import firestore

def populate_local_charges(db, data):
    """
    Populates the 'localCharges/default' document in Firestore with the provided data.

    Args:
        db: An initialized Firestore client instance.
        data: A dictionary containing the local charges data.
    """
    collection_name = "localCharges"
    document_id = "default"

    doc_ref = db.collection(collection_name).document(document_id)
    doc_ref.set(data)
    print(f"Successfully populated document '{document_id}' in collection '{collection_name}'.")
    print(f"Data written: {data}")

if __name__ == "__main__":
    print("Starting Firestore population script...")

    # Initialize Firestore client
    # This will use the default credentials configured in your environment
    try:
        db = firestore.Client()
        print("Firestore client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Firestore client: {e}")
        print("Please ensure you have authenticated and your project is configured correctly.")
        exit()

    print("Local charges data defined.")
    # print(f"Data to be written: {LOCAL_CHARGES_DATA}") # For debugging if needed

    try:
        populate_local_charges(db, LOCAL_CHARGES_DATA)
        print("Firestore population completed successfully.")
    except Exception as e:
        print(f"An error occurred during Firestore population: {e}")

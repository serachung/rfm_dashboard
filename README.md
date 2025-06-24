# RFV WhatsApp Dashboard

Instructions to run... for dummies

1️⃣ Install Python → python.org

2️⃣ Install required libraries:
```pip install -r requirements.txt```

3️⃣ Set up your Google Service Account and download service_account.json.

4️⃣ Fill out .env file:
```GOOGLE_SHEET_URL="your_google_sheet_url"
MIRE_API_SELLER_ID="your_seller_id"
MIRE_API_BASE_URL="https://mire.omnni.com.br/api"
GOOGLE_SERVICE_ACCOUNT_FILE="config/service_account.json"``` 

5️⃣ Run the app:
```streamlit run app.py```
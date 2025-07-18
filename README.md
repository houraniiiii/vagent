# EC2 prep commands
sudo yum install git
git clone https://github.com/KIPPS-AI/continental-re-vb.git

# continental-re-vb

1. Add missing env variables to the .env file

2. Set up virtual env
`python3.12 -m venv .venv`

3. Activate virtual env 
(Linux/Mac)
`source .venv/bin/activate`
(Windows)
`.venv\Scripts\activate`

4. Install Requirements -
`pip install -r requirements.txt`

5. Start livekit agent (on dev env)-
`python -m voice_agent dev`

6. Start livekit agent (on prod env)-
`python -m voice_agent start`


## Steps for Google Sheet Integration -

### Step 1: Go to Google Cloud Console

Open [https://console.cloud.google.com/](https://console.cloud.google.com/)

### Step 2: Create or Select a Project

* Click on the project dropdown in the top-left corner.
* Click **"New Project"** or select an existing one.
* Give it a name and click **Create**.

### Step 3: Enable Google Sheets API

* After selecting your project, go to **Navigation Menu (☰) > APIs & Services > Library**
* Search for **"Google Sheets API"**
* Click on the result and then click **Enable**

### Step 4: Create Service Account Credentials

* Go to **Navigation Menu > APIs & Services > Credentials**
* Click **+ Create Credentials > Service account**
* Fill in a name and description, click **Create and Continue**
* Skip roles for now (unless needed) and click **Done**

#### Add Key to Service Account

* Click on the newly created service account to edit it
* Go to the **"Keys"** tab
* Click **Add Key > Create new key > JSON**
* Download the JSON file – this is your credentials file used in the script
* Rename it to `google_credentials.json` and place it in your code folder (e.g., `CONTINENTAL-RE-VB`)

---

## Share the Google Sheet

### Step 5: Share Your Sheet

* Open your Google Sheet and click **Share**
* Enter the **service account’s email** (from the JSON file, e.g., `xyz@your-project-id.iam.gserviceaccount.com`)
* Give it **Viewer** or **Editor** access

---

Let me know if you want this in a `.md` file too!




### Setup trunking on twilio -
https://docs.livekit.io/sip/quickstarts/configuring-twilio-trunk/

### Setup trunking on plivo -
https://docs.livekit.io/sip/quickstarts/configuring-plivo-trunk/

### Command for inbound telephony integration

```python telephony.py inbound --phone-number <phone_number>```
```python telephony.py inbound --phone-number +16504071887```
```python3 telephony.py inbound --phone-number +17743456127```


### Command for outbound telephony integration


```python telephony.py outbound --phone-number <phone_number> --sip-trunk-uri <trunk-uri-without-prefix> --username <username> --password <password>```

```python telephony.py outbound --phone-number +16504071887 --sip-trunk-uri continental-test.pstn.twilio.com --username continental --password Continental@123456```

### Command for making outbound Call
First make a json file called sip_participant.json as given in the repo
Then Run the command
```lk sip participant create sip-participant.json```


### Setting up cron for data refresh every 4 hours
1. update virtual env on sheet_data_refresh.py file line 1
2. `chmod +x ./sheet_data_refresh.py`
3. `crontab -e`
4. `0 */4 * * * <your-venv-path>/bin/python3 <full_path>/sheet_data_refresh.py >> /home/user/scripts/myscript.log 2>&1`
`0 */4 * * * /home/ec2-user/continental-re-vb/.venv/bin/python3.12 /home/ec2-user/continental-re-vb/sheet_data_refresh.py /home/ec2-user/myscript.log 2&1`


### Livekit CLI set up
https://docs.livekit.io/home/cli/cli-setup/


## Livekit CLI commands for checking or deleting SIP integrations -

### List Inbound Trunks
`lk sip inbound list`

### List dispatch Rules
`lk sip dispatch list`

## Delete Inbound Trunks
`lk sip inbound delete <trunk_id>`

### Delete dispatch Rules
`lk sip dispatch delete <dispatch_id>`

### List Outbound Trunks
`lk sip outbound list`

### Delete Outbound Trunks
`lk sip outbound delete <trunk_id>`


### If you want to run the RAG file
`lk

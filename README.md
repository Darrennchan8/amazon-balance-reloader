# WORK IN PROGRESS! THIS PROJECT IS NOT FUNCTIONAL YET.

# Amazon Balance Loader
This is a Flask server that provides functionality to refill the gift card balance of an associated Amazon account.

## Motivation
Many credit card companies close credit cards due to inactivity, which can lead to a dip one's personal credit score. Sources:
[1](https://www.nerdwallet.com/article/credit-cards/credit-card-cancelled-due-inactivity),
[2](https://www.quickenloans.com/blog/credit-card-inactivity-impact-credit-score),
[3](https://www.equifax.com/personal/education/credit/report/inactive-credit-card-account-closed/),
[4](https://www.moneyunder30.com/will-my-credit-score-go-down-if-a-credit-card-company-closes-my-account-for-non-use),
[5](https://www.creditkarma.com/credit-cards/i/keep-accounts-active).

When maximizing credit card rewards, especially with cards that have rotating categories or older credit cards, one might not have any reason
to a particular card for an extended period of time due to the rewards structure, risking account closure due to credit card inactivity.

This project seeks to provide a means to automatically charge any amount against your credit/debit card(s) to mitigate credit card inactivity.

## Local Setup
### Prerequisites
- Python 3.8 or greater
- pip3

### Setup
A typical flow for local setup follows:
```bash
# (Recommended) Create a python virtual environment.
python3 -m pip install virtualenv
python3 -m venv env
source env/bin/activate # Activate the virtual environment. You'll need to run this for each new terminal instance.

# Install necessary dependencies.
pip install -r requirements.txt

# (Recommended) Enable pre-commit hooks for style linting and more.
pre-commit install
```

### Cloud Firestore Integration
Before running, you'll need to create a [GCP Firestore](https://cloud.google.com/firestore/docs/quickstart-servers#create_a_in_native_mode_database) instance
and [generate credentials for `App Engine default service account`](https://console.cloud.google.com/apis/credentials/serviceaccountkey).
You'll need to provide authentication credentials to your application code by setting the environment variable GOOGLE_APPLICATION_CREDENTIALS. Example:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/amazon-balance-reloader/service-account.json"
```
Note that for our purposes the role of `Cloud Datastore User` will suffice.

### Webdriver Server
This application also needs to connect to a chromedriver instance. In this case, we can use
[selenium/standalone-chrome](https://hub.docker.com/r/selenium/standalone-chrome/):
```bash
docker run -d -p 4444:4444 -v /dev/shm:/dev/shm selenium/standalone-chrome
```

To debug `amazon_balance_reloader`, it will be helpful to be able to see what's being automated. In this case, you'll need to download
[selenium](https://www.selenium.dev/downloads/) and [chromedriver](https://chromedriver.chromium.org/downloads) and run the following:
```bash
java "-Dwebdriver.chrome.driver=./chromedriver" -jar ./selenium-server-standalone.jar
```

## Running Locally
Run `main.py` to start a development server on port 8080:
```bash
python3 main.py
```

Visit `http://127.0.0.1:8080/` to view an HTML dashboard containing a list of recent transactions and cards.

### Usage
This app is controlled via a REST api. Here are the routes and their descriptions:

Reload the Amazon gift card balance by using a specified card to charge a specified amount.\
`GET` `/reload?card=[CARD_NUMBER]&amount=[AMOUNT]`
 - CARD_NUMBER: 4 digits corresponding to the last 4 digits of a credit card number.
 - AMOUNT: A positive floating-point number. Note that Amazon imposes a minimum reload amount of `$0.50`.

Reload the Amazon gift card balance by charging all cards associated with the Amazon account.\
`GET` `/reloadAll?amount=[AMOUNT]`
 - AMOUNT: A positive floating-point number. Note that Amazon imposes a minimum reload amount of `$0.50`.

## Cloud Setup & Deployment
This project is preconfigured for [Google App Engine](https://cloud.google.com/appengine/docs/standard/python3) deployment.

Here are the steps for initial deployment:
1. Follow [these steps](https://cloud.google.com/appengine/docs/standard/python3/quickstart#before-you-begin) to create a new GCP project.
2. Run `gcloud app deploy` and select the target project.
3. Run `gcloud app browse` to open the dashboard hosted by App Engine.

### Compute Engine Webdriver Server
With proper configuration, a remote chromedriver instance can run on even a f1-micro instance.

When creating a new VM instance, deploy the [selenium/standalone-chrome](https://hub.docker.com/r/selenium/standalone-chrome/)
container image to the VM instance. Additionally, add a network tag (ex: `chromedriver`) for
[firewall configuration](https://cloud.google.com/vpc/docs/using-firewalls#creating_firewall_rules). Ingress traffic should be enabled for tcp port 4444
matching the previously used network tag.

It's also important that Google fluentd (stackdriver-logging.service) can utilize a significant amount of memory, which makes execution infeasible on
f1-micro instances [(Example)](https://serverfault.com/q/980569).\
Execute these commands to disable it for the compute instance:
```bash
gcloud compute instances add-metadata <INSTANCE_NAME> --metadata="google-logging-enabled=false"
gcloud compute instances add-metadata <INSTANCE_NAME> --metadata="google-monitoring-enabled=false"
```
It is not possible to set the `google-logging-enabled=false` metadata through the web UI. In fact, changing any configuration for the instance through web UI will automatically set `google-logging-enabled=true`.

### Automated Builds
Follow [these steps](https://cloud.google.com/source-repositories/docs/integrating-with-cloud-build) to integrate with Cloud Build Triggers for GitHub.
Build config files are already configured.

### Automated Reloading
Consider [Google Cloud Scheduler](https://cloud.google.com/scheduler) or
[cron.yaml](https://cloud.google.com/appengine/docs/standard/python3/scheduling-jobs-with-cron-yaml) to automatically ping `/reloadAll` periodically.

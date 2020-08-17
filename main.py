import traceback
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from secrets import get_card_names
from secrets import get_cards
from secrets import get_credentials
from secrets import SecurityException
from sys import argv
from time import sleep

from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
from google.cloud import firestore
from werkzeug.exceptions import BadRequest

from amazon_balance_reloader import AmazonBalanceReloaderException
from amazon_balance_reloader import LocalAmazonBalanceReloader
from amazon_balance_reloader import RemoteAmazonBalanceReloader
from compute_session import ComputeSession
from compute_session import ComputeSessionException
from compute_session import is_app_engine_environment
from compute_session import MockComputeSession
from compute_session import project_id

app = Flask(__name__)
db = firestore.Client()


def gae_dashboard_url():
    return f"https://console.cloud.google.com/appengine?project={project_id()}"


def compute_instances_url():
    return f"https://console.cloud.google.com/compute/instances?project={project_id()}"


def cloud_log_url(start, end):
    return (
        "https://console.cloud.google.com/logs/query;query=resource.type%3D%22gae_app%22;"
        f'timeRange={(start - timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}%2F'
        f'{(end + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}?'
        f"project={project_id()}"
    )


@app.route("/")
def index():
    transactions = [
        transaction.to_dict() for transaction in db.collection("transactions").stream()
    ]
    transactions.sort(
        key=lambda transaction: transaction["timestamp_end"], reverse=True
    )
    transactions = [
        {
            "timestamp": transaction["timestamp_start"].timestamp() * 1000,
            "timestamp_str": transaction["timestamp_start"].strftime("%x %X (UTC)"),
            "time_elapsed": (
                transaction["timestamp_end"] - transaction["timestamp_start"]
            ).total_seconds()
            * 1000,
            "time_elapsed_str": f'{round((transaction["timestamp_end"] - transaction["timestamp_start"]).total_seconds())} seconds',
            "app_engine_url": transaction["app_engine"] and gae_dashboard_url(),
            "compute_engine_url": transaction["compute_instance_webdriver"]
            and compute_instances_url(),
            "log_url": cloud_log_url(
                transaction["timestamp_start"], transaction["timestamp_end"]
            )
            if transaction["app_engine"]
            else None,
            "cards": transaction["cards"],
            "amount": "${:,.2f}".format(transaction["amount"]),
            "success": transaction["success"],
            "message": f'Some cards failed to reload: { ", ".join(cs[0] for cs in zip(transaction["cards"], transaction["success"]) if not cs[1]) }'
            if True in transaction["success"] and False in transaction["success"]
            else f'Successfully reloaded {len(transaction["cards"])} cards!'
            if True in transaction["success"]
            else f'Failed to reload {len(transaction["cards"])} cards!',
        }
        for transaction in transactions
    ]
    return render_template("status.html", transactions=transactions)


def reload_batch(credentials, cards, amount):
    result = {
        "timestamp_start": datetime.now(timezone.utc),
        "app_engine": is_app_engine_environment(),
        "compute_instance_webdriver": is_app_engine_environment()
        or "--compute-instance-webdriver" in argv,
        "cards": list(cards.keys()),
        "amount": amount,
        "success": [],
        "timestamp_end": None,
    }
    try:
        if not result["compute_instance_webdriver"]:
            pass
        with ComputeSession("standalone-chrome") if result[
            "compute_instance_webdriver"
        ] else MockComputeSession("127.0.0.1") as session:
            with RemoteAmazonBalanceReloader(f"{session.remote_ip()}:4444") if result[
                "compute_instance_webdriver"
            ] else LocalAmazonBalanceReloader() as reloader:
                reloader.authenticate(credentials["username"], credentials["password"])
                for card in cards.values():
                    try:
                        reloader.reload(card, amount)
                        result["success"].append(True)
                    except AmazonBalanceReloaderException:
                        result["success"].append(False)
                        traceback.print_exc()
    except (ComputeSessionException, AmazonBalanceReloaderException):
        result["success"].extend([False] * (len(cards) - len(result["success"])))
        traceback.print_exc()
    result["timestamp_end"] = datetime.now(timezone.utc)
    db.collection("transactions").add(result)
    return result


def validate_and_reload_batch(key, cards, amount):
    if (
        amount <= 0
        or len(cards) == 0
        or False in [card in get_card_names() for card in cards]
    ):
        raise BadRequest()
    try:
        return reload_batch(
            get_credentials(key),
            {
                name: number
                for (name, number) in get_cards(key).items()
                if name in cards
            },
            amount,
        )
    except SecurityException:
        # Block for 5 seconds to mitigate brute-force key attacks.
        sleep(5)
        raise BadRequest()


@app.route("/reload")
def reload():
    key = request.args.get("key", "")
    cards = request.args.get("cards", "").split(",")
    amount = request.args.get("amount", 0, float)
    return jsonify({**validate_and_reload_batch(key, cards, amount), "cards": None})


@app.route("/reloadAll")
def reload_all():
    key = request.args.get("key", "")
    amount = request.args.get("amount", 0, float)
    return jsonify(
        {**validate_and_reload_batch(key, get_card_names(), amount), "cards": None}
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)

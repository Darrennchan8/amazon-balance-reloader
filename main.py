from flask import Flask, render_template
from enum import Enum

app = Flask(__name__)

@app.route("/")
def index():
    mock_transactions = [{
        "timestamp": "05/29/2020 08:24 EST",
        "card": "Uber",
        "amount": "$0.50",
        "success": True
    },{
        "timestamp": "05/29/2020 08:24 EST",
        "card": "Discover",
        "amount": "$0.50",
        "success": True
    }, {
        "timestamp": "06/29/2020 08:24 EST",
        "card": "Uber",
        "amount": "$0.50",
        "success": False,
        "message": "Unable to refill the balance of this card."
    }, {
        "timestamp": "06/29/2020 08:24 EST",
        "card": "Discover",
        "amount": "$0.50",
        "success": False,
        "message": "Unable to refill the balance of this card."
    }]
    mock_cards = [{
        "name": "Uber",
        "number": "**** **** **** 1234"
    }, {
        "name": "Discover",
        "number": "**** **** **** 4321"
    }]
    return render_template("status.html", transactions=mock_transactions, cards=mock_cards)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)

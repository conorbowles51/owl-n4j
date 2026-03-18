"""
Auto-categorize uncategorized transactions based on name and summary patterns.
Matches the existing manually-assigned categories.

Usage:
    python categorize_transactions.py              # Dry run (default)
    python categorize_transactions.py --apply      # Apply changes to Neo4j
"""

import os
import re
import sys
from collections import Counter
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
pwd = os.getenv("NEO4J_PASSWORD", "")

APPLY = "--apply" in sys.argv


def classify(name: str, summary: str, amount_raw: str, labels: list[str]) -> str | None:
    """Return a category string or None if no match."""
    n = name.lower()
    s = summary.lower()
    both = f"{n} {s}"

    # --- System / non-financial noise (zero-value or meta entries) ---
    if any(x in n for x in [
        "signin", "sign in", "targeted ad", "mobile app detection",
        "marketing ad", "search results", "velocity check",
        "image & velocity", "page load", "app detection",
        "add mobile number", "add email",
    ]):
        return "Ignore"

    # --- Zelle ---
    if "zelle" in both:
        return "Zelle Transactions Need More Info"

    # --- Cash App ---
    if "cash app" in both or "cashapp" in both or "square cash" in both:
        return "Cash App"

    # --- Crypto ---
    if any(x in both for x in ["crypto", "bitcoin", "coinbase", "blockchain", "ethereum", "binance"]):
        return "Crypto"

    # --- WorldRemit / international transfers ---
    if any(x in both for x in ["worldremit", "world remit", "remitly", "western union", "moneygram"]):
        return "Transfer"

    # --- ATM ---
    if "atm" in n:
        if any(x in n for x in ["withdraw", "debit"]):
            return "ATM Cash Withdrawal"
        return "ATM Cash Deposit"

    # --- Check card ---
    if "checkcard" in n or "check card" in n or "checkcard" in s:
        return "Check Card"

    # --- Overdraft / NSF fees ---
    if any(x in n for x in ["overdraft", "nsf fee", "insufficient fund"]):
        return "Bank Fees"

    # --- ACH returned items ---
    if "ach returned" in n or "ach return" in n or "returned item" in n:
        return "Bank Fees"

    # --- Interest charges ---
    if any(x in n for x in ["interest charge", "interest payment", "interest on"]):
        return "Bank Fees"

    # --- Minimum charge / late fee ---
    if any(x in n for x in ["minimum charge", "late fee", "late payment", "finance charge"]):
        return "Bank Fees"

    # --- Cash reward / bank reward ---
    if "cashreward" in both or "cash reward" in both:
        return "Bank Fees"

    # --- Insurance ---
    if "insurance" in both or "geico" in both or "allstate" in both or "state farm" in both:
        return "Insurance"

    # --- Loan / PPP ---
    if any(x in both for x in ["ppp loan", "loan payment", "loan disbursement", "loan request"]):
        return "Loan Payment"
    if "fdgl" in both or ("lease payment" in both and "ach" in both):
        return "Rent/Lease"

    # --- Payroll / salary / SSI ---
    if any(x in both for x in ["payroll", "salary", "wage", "ssi payment", "social security", "1099-nec", "nonemployee compensation"]):
        return "Payroll/Salary"

    # --- ACH / electronic payments (after more specific checks) ---
    if any(x in n for x in ["ach debit", "ccd debit", "electronic payment", "ach credit"]):
        return "Transfer"

    # --- Deposit (not transfer) ---
    if "deposit" in n and "transfer" not in n and "check" not in n:
        return "ATM Cash Deposit"

    # --- Mobile check deposit ---
    if "mobile check deposit" in n or "remote deposit" in n or "mcd deposit" in n:
        return "Check Payment"

    # --- Check payment ---
    if any(x in n for x in ["check payment", "check #", "check number", "counter check"]):
        return "Check Payment"

    # --- Transfer ---
    if any(x in both for x in [
        "transfer", "immediate mobile", "one-time transfer",
        "moneysend", "money send", "p2p",
    ]):
        return "Transfer"

    # --- Person-to-person payments (Payment to/from Name) ---
    if re.match(r"payment (to|from) ", n):
        return "Mobile Transactions"

    # --- Account balances / totals / statement lines ---
    if any(x in n for x in [
        "total deposits", "total withdrawals", "account balance",
        "statement closing", "billing cycle", "closing balance",
        "opening balance", "previous balance",
    ]):
        return "Account Balances"

    # --- Retail / grocery / gas / food merchants ---
    retail_merchants = [
        "wal-mart", "walmart", "aldi", "costco", "target",
        "safeway", "giant", "food lion", "kroger", "publix",
        "whole foods", "trader joe", "supermarket", "grocery",
        "dollar tree", "dollar general", "family dollar",
    ]
    gas_merchants = [
        "shell", "sunoco", "exxon", "mobil", "chevron", "bp ",
        "citgo", "wawa", "speedway", "gas station", "7-eleven",
        "seven eleven", "royal farms",
    ]
    food_merchants = [
        "mcdonald", "burger king", "wendy", "subway",
        "chick-fil", "popeye", "taco bell", "pizza",
        "domino", "starbucks", "dunkin", "checkers",
        "chipotle", "panera", "ihop", "waffle",
        "liquor", "restaurant",
    ]
    if any(x in both for x in retail_merchants):
        return "Personal"
    if any(x in both for x in gas_merchants):
        return "Personal"
    if any(x in both for x in food_merchants):
        return "Personal"

    # --- General purchases ---
    if "purchase" in n and any(x in both for x in ["pos", "debit card", "visa", "mastercard"]):
        return "Check Card"
    if "purchase at" in n or "purchase -" in n:
        return "Personal"

    # --- Utility ---
    if any(x in both for x in [
        "pepco", "bge", "electric", "water bill", "gas bill",
        "comcast", "verizon", "t-mobile", "tmobile", "at&t",
        "sprint", "phone bill", "internet bill", "utility",
    ]):
        return "Utility"

    # --- Subscription ---
    if any(x in both for x in [
        "netflix", "spotify", "hulu", "disney+", "amazon prime",
        "apple.com", "google play", "subscription", "monthly fee",
    ]):
        return "Subscription"

    # --- Rent ---
    if any(x in both for x in ["rent payment", "rent for", "lease payment"]):
        return "Rent/Lease"

    # --- Filing / legal ---
    if any(x in both for x in ["filing payment", "legal", "attorney", "court", "bail"]):
        return "Other"

    # --- Cash withdrawal at branch ---
    if "cash withdrawal" in n or ("withdrawal" in n and "branch" in n):
        return "ATM Cash Withdrawal"

    # --- Generic withdrawal ---
    if "Withdrawal" in labels or "withdrawal" in n:
        return "ATM Cash Withdrawal"

    # --- Money received / sent (P2P via summary) ---
    if "money received" in n or "money sent" in n:
        return "Mobile Transactions"

    # --- Debit MoneySend ---
    if "moneysend" in n or "money send" in n:
        return "Mobile Transactions"

    # --- Payment due / credit card payment ---
    if "payment due" in n or "minimum payment" in n:
        return "Loan Payment"

    # --- Capital One / Amex / credit card payments ---
    if any(x in both for x in ["capital one", "amex", "american express", "credit card"]):
        return "Loan Payment"

    # --- USPS / shipping ---
    if "usps" in both or "ups " in both or "fedex" in both:
        return "Other"

    # --- Vehicle ---
    if "vehicle" in both or "car payment" in both or "auto loan" in both:
        return "Loan Payment"

    # --- Property / real estate ---
    if any(x in both for x in ["property", "real estate", "commission", "listing agent", "selling agent"]):
        return "Real Estate Transaction - Personal"

    # --- Generic "Transaction on DATE" — try summary-based classification ---
    if n.startswith("transaction") and len(n) < 40:
        # Try to classify from summary
        if "zelle" in s:
            return "Zelle Transactions Need More Info"
        if "cash app" in s:
            return "Cash App"
        if "atm" in s and "deposit" in s:
            return "ATM Cash Deposit"
        if "atm" in s and "withdraw" in s:
            return "ATM Cash Withdrawal"
        if "check" in s and ("deposit" in s or "mobile" in s):
            return "Check Payment"
        if "overdraft" in s:
            return "Bank Fees"
        if "transfer" in s:
            return "Transfer"
        if any(x in s for x in ["presented on", "posted on", "account number"]):
            return "Checking Account"
        # Fall through to uncategorized

    # --- Payment on DATE (generic) ---
    if re.match(r"payment on \d", n):
        if "zelle" in s:
            return "Zelle Transactions Need More Info"
        if "check" in s:
            return "Check Payment"
        if "transfer" in s:
            return "Transfer"
        return "Checking Account"

    # --- Deposit Transaction on DATE ---
    if "deposit transaction" in n:
        return "Checking Account"

    # --- CES Transaction ---
    if "ces transaction" in n:
        return "Other"

    # --- Generic "Payment" with a person name ---
    if n.startswith("payment") and ("$" in n or re.search(r"\d", n)):
        return "Mobile Transactions"

    # --- Cashloan / repayment / planned payment between individuals ---
    if any(x in n for x in ["cashloan", "cash loan", "repayment", "planned cash"]):
        return "Mobile Transactions"

    # --- Payment discussed / payment for period ---
    if "payment discussed" in n or "payment for" in n:
        return "Mobile Transactions"

    # --- TRN DEBIT ---
    if "trn debit" in n or "trn credit" in n:
        return "Transfer"

    # --- New Loan / Toyota / auto loan ---
    if "new loan" in n or "toyota" in both or "auto" in n:
        return "Loan Payment"

    # --- Total payment request / billing ---
    if "total payment" in n or "billing" in n:
        return "Loan Payment"

    # --- Invoice ---
    if "invoice" in n:
        return "Other"

    # --- Bank Transactions for MONTH ---
    if re.match(r"bank transactions for", n):
        return "Account Balances"

    # --- Check given / deposited check ---
    if "check given" in n or "deposited" in n and "check" in n:
        return "Check Payment"

    # --- Reversal ---
    if "reversal" in n:
        return "Bank Fees"

    # --- Money returned ---
    if "money returned" in n:
        return "Transfer"

    # --- Transaction to/from person ---
    if re.match(r"transaction (to|from|with) ", n):
        return "Mobile Transactions"

    # --- Transaction involving $ ---
    if "transaction involving" in n:
        return "Other"

    # --- Square Inc ---
    if "square" in both and "cash" not in both:
        return "Check Card"

    # --- Remaining generic "Transaction on DATE", "Transaction serial", "Transaction-ID", bare "Transaction" ---
    if re.match(r"transaction(\s+(on|at|serial|dated|\d|-)|\s*$)", n):
        return "Checking Account"

    # --- Transaction for MONTH ---
    if re.match(r"transaction for ", n):
        return "Checking Account"

    # --- Deposit of / deposit to ---
    if n.startswith("deposit of") or n.startswith("deposit to"):
        return "Checking Account"

    # --- Remaining with "sent" or "received" ---
    if "sent" in n or "received" in n:
        return "Mobile Transactions"

    # --- Remaining with "$" in name (likely financial discussion) ---
    if "$" in n and any(x in n for x in ["payment", "fund", "cash"]):
        return "Other"

    # --- Transaction-ID (e.g. Transaction-9100478746) ---
    if re.match(r"transaction[- ]\d", n) or re.match(r"transaction (by|reference|ref)", n):
        return "Checking Account"

    # --- WF Store / Wells Fargo payments ---
    if "wf store" in n or "wells fargo" in both:
        return "Loan Payment"

    # --- Point of sale debit/credit ---
    if "point of sale" in n or "pos debit" in n or "pos credit" in n:
        return "Check Card"

    # --- Amazon / AMZN ---
    if "amzn" in both or "amazon" in both:
        return "Personal"

    # --- Uber / Lyft ---
    if "uber" in both or "lyft" in both:
        return "Personal"

    # --- Google (storage, adsense, etc) ---
    if "google" in both:
        if "adsense" in both or "income" in both:
            return "Income"
        return "Subscription"

    # --- PayPal ---
    if "paypal" in both:
        return "Transfer"

    # --- Robinhood / investment ---
    if "robinhood" in both or "investment" in both or "stock" in both:
        return "Crypto"

    # --- Marathon / Arathon / petro / gas ---
    if any(x in both for x in ["marathon", "arathon", "petro", "citgo"]):
        return "Personal"

    # --- Southwest / airline ---
    if any(x in both for x in ["southwes", "southwest", "airline", "delta air", "united air", "american air"]):
        return "Personal"

    # --- Delivery charge ---
    if "delivery" in n:
        return "Personal"

    # --- Adjustment / interest decrease ---
    if "adjustment" in n or "interest decrease" in n or "interest increase" in n:
        return "Bank Fees"

    # --- Filing / articles of organization ---
    if "filing" in n or "articles of" in both:
        return "Other"

    # --- Business income / advertising expense / gross income ---
    if any(x in n for x in ["business income", "gross income", "advertising expense"]):
        return "Income"

    # --- Business Transactions YEAR ---
    if re.match(r"business transactions", n):
        return "Income"

    # --- Bank of America card ---
    if "bank of america card" in n:
        return "Ignore"

    # --- SSI / social security ---
    if "ssi" in n:
        return "Payroll/Salary"

    # --- Agency services / direct pay ---
    if "agency services" in n or "direct pay" in n:
        return "Other"

    # --- Visa Direct ---
    if "visa direct" in n:
        return "Transfer"

    # --- IDT / calling ---
    if "idt" in n or "calling" in n or "intl calling" in both:
        return "Personal"

    # --- Pattern of payments ---
    if "pattern of" in n:
        return "Other"

    # --- US Eagle / corp purchase ---
    if "purchase" in n:
        return "Personal"

    # --- LIDL / Metro Sup / supermarket ---
    if any(x in both for x in ["lidl", "metro sup"]):
        return "Personal"

    # --- Emergency funding ---
    if "emergency" in n or "funding" in n:
        return "Other"

    # --- Remaining "Transaction via/with SERVICE" ---
    if re.match(r"transaction (via|with) ", n):
        return "Transfer"

    # --- National Telegraph ---
    if "national telegraph" in both:
        return "Other"

    # --- Check Transaction ---
    if "check transaction" in n:
        return "Check Payment"

    # --- Online banking payment / online payment ---
    if "online banking" in n or "online payment" in n:
        return "Transfer"

    # --- Counter credit ---
    if "counter credit" in n:
        return "ATM Cash Deposit"

    # --- Reward from bank ---
    if "reward" in n:
        return "Bank Fees"

    # --- Refund ---
    if "refund" in n:
        return "Reimbursement"

    # --- Car wash / service center / local merchants by name ---
    if any(x in both for x in ["car wash", "service center", "photo press"]):
        return "Personal"

    # --- Transactions from DATE range ---
    if re.match(r"transactions from", n):
        return "Checking Account"

    # --- Profit from / expenses / Schedule C ---
    if any(x in n for x in ["profit from", "expenses", "schedule c", "reported income"]):
        return "Income"

    # --- Wire request ---
    if "wire" in n:
        return "Transfer"

    # --- Card Transaction by ---
    if "card transaction" in n:
        return "Check Card"

    # --- Application Transaction / Signature Cards / Certified Checks ---
    if any(x in n for x in ["application transaction", "signature card", "certified check", "checks and debits"]):
        return "Ignore"

    # --- SQC payment / Square payment ---
    if "sqc" in n or "square" in both:
        return "Check Card"

    # --- Transaction associated with ---
    if "transaction associated" in n:
        return "Other"

    # --- Bank transaction on ---
    if "bank transaction" in n:
        return "Checking Account"

    # --- Payment Transaction (generic) ---
    if "payment transaction" in n:
        return "Checking Account"

    # --- Remaining merchant-like names (CITY, STATE pattern) ---
    if re.search(r" - [A-Z][a-z]+,? [A-Z]{2}$", name or ""):
        return "Personal"

    # --- Phone Payment ---
    if "phone payment" in n:
        return "Transfer"

    # --- ACH Transaction ---
    if "ach transaction" in n:
        return "Transfer"

    # --- Financial Summary / monthly summary ---
    if "financial summary" in n or "monthly summary" in n:
        return "Account Balances"

    # --- Beginning/ending balance ---
    if "beginning balance" in n or "ending balance" in n or "closing balance" in n:
        return "Account Balances"

    # --- Account statement closure ---
    if "statement closure" in n or "account statement" in n:
        return "Account Balances"

    # --- Service fees ---
    if "service fee" in n:
        return "Bank Fees"

    # --- Checks from DATE range ---
    if re.match(r"checks from", n):
        return "Check Payment"

    # --- E-ZPass ---
    if "ezpass" in n or "e-zpass" in n or "ez pass" in n:
        return "Personal"

    # --- Special Terms Transaction ---
    if "special terms" in n:
        return "Checking Account"

    # --- Apple recurring ---
    if "apple" in n and ("recurring" in n or "payment" in n):
        return "Subscription"

    # --- DC Government / government payment ---
    if "government" in n or "dc gov" in n:
        return "Other"

    # --- Payments and Other Credits ---
    if "payments and other" in n or "other credits" in n:
        return "Checking Account"

    # --- Payment (bare) / Payment - Thank You ---
    if n.strip() in ["payment", "payment - thank you"]:
        return "Checking Account"

    # --- March/April/etc Transactions ---
    if re.match(r"(january|february|march|april|may|june|july|august|september|october|november|december) transactions", n):
        return "Checking Account"

    # --- New Account Discount ---
    if "discount" in n:
        return "Bank Fees"

    # --- Remaining local merchants (Farmer's, market, bar, etc.) ---
    if any(x in both for x in ["farmer", "market", "bar ", "piano bar", "meat shop"]):
        return "Personal"

    # --- Remaining NationalTelegraph ---
    if "nationaltelegraph" in both:
        return "Other"

    # --- Check Deposit ---
    if "check deposit" in n:
        return "Check Payment"

    # --- Monthly maintenance fee ---
    if "maintenance fee" in n:
        return "Bank Fees"

    # --- Sales tax ---
    if "sales tax" in n:
        return "Other"

    # --- Deferred interest ---
    if "deferred interest" in n:
        return "Bank Fees"

    # --- Charity / donation ---
    if "charity" in n or "donation" in n:
        return "Charitable Donations"

    # --- DC Parking ---
    if "parking" in n:
        return "Personal"

    # --- Monthly payment ---
    if "monthly payment" in n:
        return "Loan Payment"

    # --- License and Registration ---
    if "license" in n or "registration" in n:
        return "Other"

    # --- Tax / Form 941 ---
    if "tax" in n or "form 941" in n:
        return "Tax - Related"

    # --- MasterCard debit ---
    if "mastercard" in n:
        return "Check Card"

    # --- Recurring transaction ---
    if "recurring" in n:
        return "Subscription"

    # --- Account summary / summary of activity ---
    if "account summary" in n or "summary of" in n:
        return "Account Balances"

    # --- Total Cash Price ---
    if "total cash" in n:
        return "Account Balances"

    # --- ACH Electronic Credit ---
    if "ach electronic" in n:
        return "Transfer"

    # --- Points earned ---
    if "points earned" in n:
        return "Ignore"

    # --- EveryDay Checking / Membership Savings ---
    if "checking account" in n or "savings account" in n:
        return "Checking Account"

    # --- Payment on account / Payment Thank You / MCBNAE ---
    if n.startswith("payment"):
        return "Checking Account"

    # --- Remaining local merchants / named transactions ---
    if "transaction" in n and len(n) < 50:
        return "Checking Account"

    return None


def main():
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE (n:Transaction OR n:Payment OR n:Invoice OR n:Deposit OR n:Withdrawal)
            AND (n.financial_category IS NULL OR n.financial_category = "")
            RETURN n.key AS key, n.name AS name, n.summary AS summary,
                   n.amount AS amount, labels(n) AS labels
        """)
        records = [(r["key"], r["name"], r["summary"], str(r["amount"] or ""), r["labels"]) for r in result]

    print(f"Total uncategorized transactions: {len(records)}\n")

    categorized = []
    uncategorized = []
    category_counts = Counter()

    for key, name, summary, amount, labels in records:
        cat = classify(name or "", summary or "", amount, labels or [])
        if cat:
            categorized.append((key, name, cat))
            category_counts[cat] += 1
        else:
            uncategorized.append((key, name, amount, summary))

    print(f"{'Category':<45s} {'Count':>7s}")
    print("-" * 55)
    for cat, cnt in category_counts.most_common():
        print(f"  {cat:<43s} {cnt:>7d}")
    print("-" * 55)
    print(f"  {'TOTAL CATEGORIZED':<43s} {len(categorized):>7d}")
    print(f"  {'STILL UNCATEGORIZED':<43s} {len(uncategorized):>7d}")
    print(f"  {'COVERAGE':<43s} {len(categorized)/len(records)*100:>6.1f}%")

    if uncategorized:
        print(f"\n--- Sample of remaining uncategorized (first 40) ---")
        for key, name, amount, summary in uncategorized[:40]:
            print(f"  {str(amount):>12s}  {(name or 'unnamed')[:70]}")
            if summary:
                print(f"  {'':>12s}  -> {(summary or '')[:90]}")

    if APPLY:
        print(f"\n--- APPLYING {len(categorized)} category updates to Neo4j ---")
        driver2 = GraphDatabase.driver(uri, auth=(user, pwd))
        with driver2.session() as session:
            # Batch updates in groups of 500
            batch_size = 500
            for i in range(0, len(categorized), batch_size):
                batch = categorized[i:i + batch_size]
                params = [{"key": k, "category": c} for k, _, c in batch]
                session.run("""
                    UNWIND $params AS p
                    MATCH (n {key: p.key})
                    SET n.financial_category = p.category
                """, params=params)
                print(f"  Updated {min(i + batch_size, len(categorized))}/{len(categorized)}")
        driver2.close()
        print("\nDone! All categories applied.")
    else:
        print("\n--- DRY RUN --- Pass --apply to commit changes to Neo4j.")

    driver.close()


if __name__ == "__main__":
    main()


"""
FinTech Adoption Index — Keyword Dictionary
Extended index: 13 parameters

Purpose:
1. Identify possible FinTech-related evidence in bank annual reports.
2. Support a binary adoption index after evidence verification.
3. Keep keyword matching separate from final research scoring.

Important:
A keyword match is not, by itself, proof of adoption.
"""

FINTECH_DICTIONARY = {
    "Digital Presence": [
        "digital banking",
        "digital banking channel",
        "digital channels",
        "online account opening",
        "online account opening facility",
        "digital account opening",
        "real-time account information",
        "digital banking platform",
        "online banking services",
        "digital financial services",
    ],

    "Mobile Banking": [
        "mobile banking",
        "mobile banking application",
        "mobile banking app",
        "mobile check deposit",
        "mobile cheque deposit",
        "mobile fund transfer",
        "mobile bill payment",
        "mobile banking transaction",
        "mobile banking services",
        "mobile banking notification",
    ],

    "Internet Banking": [
        "internet banking",
        "internet banking services",
        "net banking",
        "internet banking transaction",
        "online banking transaction",
        "electronic fund transfer",
        "NEFT",
        "RTGS",
        "IMPS",
    ],

    "Open Banking": [
        "open banking",
        "open API",
        "open APIs",
        "application programming interface",
        "banking API",
        "API banking",
        "third-party API",
        "API integration",
        "account aggregator",
        "account aggregation framework",
    ],

    "Cards": [
        "debit card",
        "credit card",
        "contactless card",
        "virtual card",
        "prepaid card",
        "card payment",
        "cardless transaction",
        "tap-to-pay",
        "tap and pay",
        "contactless payments card",
    ],

    "Partnerships": [
        "FinTech partnership",
        "FinTech partner",
        "FinTech collaboration",
        "technology partnership",
        "strategic technology alliance",
        "banking technology partner",
        "FinTech ecosystem",
        "co-lending partnership",
        "partnership with a FinTech",
        "collaboration with a FinTech",
    ],

    "Digital Payment Solutions": [
        "digital payment",
        "mobile wallet",
        "electronic wallet",
        "digital wallet",
        "peer-to-peer payment",
        "P2P payment",
        "contactless payment",
        "merchant payment",
        "payment gateway",
        "electronic payment",
        "digital payment platform",
    ],

    "Artificial Intelligence": [
        "artificial intelligence",
        "machine learning",
        "AI chatbot",
        "chatbot",
        "virtual assistant",
        "natural language processing",
        "NLP",
        "predictive analytics",
        "generative AI",
        "robotic process automation",
        "RPA",
        "intelligent automation",
    ],

    "Cyber Security": [
        "cybersecurity",
        "cyber security",
        "cyber threat",
        "cyber risk",
        "information security",
        "data security",
        "cyber fraud detection",
        "fraud detection system",
        "data encryption",
        "multi-factor authentication",
        "multifactor authentication",
        "security operations centre",
        "security operations center",
    ],

    "Embracing New Technology": [
        "robo-advisory",
        "robo advisory",
        "robo-advisor",
        "robo advisor",
        "automated financial advice",
        "digital wealth management",
        "automated investment advice",
        "algorithmic investment advice",
        "automated portfolio management",
    ],

    "UPI Ecosystem": [
        "Unified Payments Interface",
        "UPI",
        "BHIM UPI",
        "UPI QR",
        "UPI Lite",
        "UPI AutoPay",
        "UPI transaction",
        "UPI payment",
        "UPI merchant payment",
        "UPI ID",
        "UPI interoperability",
    ],

    "Digital Identity and eKYC": [
        "Aadhaar-based eKYC",
        "Aadhaar eKYC",
        "eKYC",
        "e-KYC",
        "electronic know your customer",
        "Video KYC",
        "V-KYC",
        "digital identity verification",
        "Aadhaar authentication",
        "digital onboarding",
        "paperless onboarding",
    ],

    "IT and Technology Investment": [
        "IT expenditure",
        "IT spend",
        "IT spending",
        "technology expenditure",
        "technology investment",
        "technology budget",
        "digital transformation investment",
        "capital expenditure on technology",
        "technology infrastructure investment",
        "expenditure on information technology",
        "IT infrastructure spending",
    ],
}


# Blockchain is recorded separately because its presence alone
# does not prove that a bank has adopted cybersecurity measures.
BLOCKCHAIN_KEYWORDS = [
    "blockchain",
    "distributed ledger technology",
    "distributed ledger",
]


# These terms are too broad to establish adoption on their own.
# They should be interpreted only when supported by surrounding text.
CONTEXT_DEPENDENT_KEYWORDS = {
    "Digital Presence": ["digital"],
    "Open Banking": ["API", "APIs"],
    "Artificial Intelligence": ["AI"],
    "UPI Ecosystem": ["QR code", "QR codes"],
    "Digital Identity and eKYC": ["Aadhaar"],
    "Cyber Security": ["security", "fraud"],
    "IT and Technology Investment": ["technology"],
}

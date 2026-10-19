
"""
FinTech Adoption Index — Text Analysis Module

This module:
1. Searches extracted annual-report text.
2. Identifies keyword matches by parameter.
3. Saves occurrence counts and evidence snippets.
4. Produces provisional scores for manual review.

A keyword match does NOT automatically prove adoption.
"""

import re
from fintech_dictionary import (
    FINTECH_DICTIONARY,
    BLOCKCHAIN_KEYWORDS,
    CONTEXT_DEPENDENT_KEYWORDS,
)


def clean_text(text):
    """Standardise text extracted from an annual report."""
    text = str(text or "")
    text = text.replace("\u00ad", "")  # Soft hyphen
    text = text.replace("\u00a0", " ")  # Non-breaking space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_pattern(keyword):
    """
    Create a case-insensitive phrase pattern.

    Allows spaces and hyphens between words, for example:
    'cyber security' can match 'cyber-security'.
    """
    parts = keyword.split()
    phrase = r"[\s\-]+".join(re.escape(part) for part in parts)
    return re.compile(
        rf"(?<!\w){phrase}(?!\w)",
        flags=re.IGNORECASE,
    )


def get_evidence_snippet(text, start, end, window=180):
    """Return nearby text to help verify a keyword match."""
    left = max(0, start - window)
    right = min(len(text), end + window)

    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""

    return prefix + text[left:right].strip() + suffix


def find_keyword_matches(text, keywords):
    """
    Find keyword occurrences and retain their positions.

    Overlapping matches are consolidated within this keyword list,
    so a phrase and its shorter overlapping phrase are not both
    counted for the same overlapping text.
    """
    matches = []

    for keyword in keywords:
        pattern = build_pattern(keyword)

        for match in pattern.finditer(text):
            matches.append({
                "keyword": keyword,
                "start": match.start(),
                "end": match.end(),
            })

    # Prefer the longest phrase when matches start at the same point.
    matches.sort(
        key=lambda item: (
            item["start"],
            -(item["end"] - item["start"]),
            item["keyword"],
        )
    )

    accepted = []

    for match in matches:
        overlaps = any(
            match["start"] < previous["end"]
            and match["end"] > previous["start"]
            for previous in accepted
        )

        if not overlaps:
            accepted.append(match)

    return sorted(accepted, key=lambda item: item["start"])


def analyse_report_text(report_text):
    """
    Analyse extracted report text against all 13 parameters.

    The provisional score indicates whether at least one dictionary
    keyword was found. It is NOT the verified research index score.
    """
    text = clean_text(report_text)
    results = {}

    for parameter, keywords in FINTECH_DICTIONARY.items():
        matches = find_keyword_matches(text, keywords)

        evidence = []

        for match in matches:
            evidence.append({
                "keyword": match["keyword"],
                "start": match["start"],
                "end": match["end"],
                "snippet": get_evidence_snippet(
                    text,
                    match["start"],
                    match["end"],
                ),
            })

        keyword_counts = {}

        for keyword in keywords:
            keyword_counts[keyword] = sum(
                match["keyword"].casefold() == keyword.casefold()
                for match in matches
            )

        # Terms requiring context are flagged for extra review.
        context_terms_found = []

        for term in CONTEXT_DEPENDENT_KEYWORDS.get(parameter, []):
            if build_pattern(term).search(text):
                context_terms_found.append(term)

        results[parameter] = {
            "occurrence_count": len(matches),
            "matched_keywords": sorted({
                match["keyword"] for match in matches
            }),
            "keyword_counts": keyword_counts,
            "context_terms_found": context_terms_found,
            "evidence": evidence,
            "provisional_score": int(bool(matches)),
            "verified_score": None,
            "review_status": "Needs manual verification",
        }

    # Blockchain is deliberately tracked separately.
    blockchain_matches = find_keyword_matches(
        text,
        BLOCKCHAIN_KEYWORDS,
    )

    results["_Blockchain review only"] = {
        "occurrence_count": len(blockchain_matches),
        "matched_keywords": sorted({
            match["keyword"] for match in blockchain_matches
        }),
        "evidence": [
            {
                "keyword": match["keyword"],
                "start": match["start"],
                "end": match["end"],
                "snippet": get_evidence_snippet(
                    text,
                    match["start"],
                    match["end"],
                ),
            }
            for match in blockchain_matches
        ],
        "note": (
            "Blockchain mentions do not automatically establish "
            "cybersecurity adoption."
        ),
    }

    return results


def calculate_verified_index(results):
    """
    Calculate the extended index using manually verified scores.

    Each of the 13 parameters must have a verified score of 0 or 1.
    Missing scores cause an error rather than silently becoming zero.
    """
    parameters = list(FINTECH_DICTIONARY.keys())
    scores = []

    for parameter in parameters:
        score = results[parameter].get("verified_score")

        if score not in (0, 1):
            raise ValueError(
                f"Verify the score for '{parameter}' first. "
                "Enter 0 or 1 in verified_score."
            )

        scores.append(score)

    total_score = sum(scores)

    return {
        "index_name": "Extended FinTech Adoption Index",
        "number_of_parameters": len(parameters),
        "total_score": total_score,
        "maximum_score": len(parameters),
        "percentage_score": round(
            total_score / len(parameters) * 100, 2
        ),
    }


if __name__ == "__main__":
    # Small test example; this is not a real bank annual report.
    sample_text = """
    The bank offers mobile banking and internet banking services.
    Customers can make UPI payments through the bank's application.
    The bank also invested in technology infrastructure.
    """

    output = analyse_report_text(sample_text)

    print("\nFINTECH TEXT-MINING TEST")
    print("=" * 50)

    for parameter, details in output.items():
        print(f"\n{parameter}")
        print(f"Occurrences: {details['occurrence_count']}")
        print(f"Provisional score: {details.get('provisional_score', 'N/A')}")

        if details.get("matched_keywords"):
            print("Matched keywords:", ", ".join(
                details["matched_keywords"]
            ))

    print("\nTest completed.")

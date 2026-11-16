from jobfit.ingest.dedup import content_hash, is_near_duplicate, minhash_signature


def test_content_hash_is_case_and_whitespace_insensitive():
    a = content_hash("  Machine Learning Engineer ", "Scandit", "Zurich")
    b = content_hash("machine learning engineer", "scandit", "zurich")
    assert a == b


def test_content_hash_differs_for_different_companies():
    a = content_hash("Machine Learning Engineer", "Scandit", "Zurich")
    b = content_hash("Machine Learning Engineer", "Squirro", "Zurich")
    assert a != b


def test_content_hash_differs_for_different_locations():
    # Same title at the same company usually means separate open reqs per
    # city, not one posting duplicated — location must be part of the key.
    a = content_hash("Technical Account Manager", "SonarSource", "Zurich")
    b = content_hash("Technical Account Manager", "SonarSource", "Geneva")
    assert a != b


def test_minhash_near_duplicate_detects_lightly_edited_posting():
    title = "Senior Machine Learning Engineer"
    original = (
        "We are looking for a Senior Machine Learning Engineer to join our Zurich team. "
        "You will build and ship production ML systems end to end, from data pipelines "
        "to model training to deployment. You will work closely with product and data "
        "engineering to turn research prototypes into reliable, scalable services that "
        "run in production every day, and you will mentor more junior engineers on the team."
    )
    # Same posting, reposted on a second board with one word changed ("office" vs "team")
    # and the company's boilerplate equal-opportunity line appended at the end.
    reposted = (
        "We are looking for a Senior Machine Learning Engineer to join our Zurich office. "
        "You will build and ship production ML systems end to end, from data pipelines "
        "to model training to deployment. You will work closely with product and data "
        "engineering to turn research prototypes into reliable, scalable services that "
        "run in production every day, and you will mentor more junior engineers on the team. "
        "We are an equal opportunity employer."
    )
    sig_a = minhash_signature(original)
    sig_b = minhash_signature(reposted)
    assert is_near_duplicate(title, sig_a, title, sig_b)


def test_minhash_does_not_flag_unrelated_postings_as_duplicates():
    title_a = "Senior Machine Learning Engineer"
    posting_a = f"{title_a}, Zurich. Build production ML systems with PyTorch."
    title_b = "Accounts Payable Specialist"
    posting_b = f"{title_b}, Warsaw. Process vendor invoices and expense claims."
    sig_a = minhash_signature(posting_a)
    sig_b = minhash_signature(posting_b)
    assert not is_near_duplicate(title_a, sig_a, title_b, sig_b)


def test_minhash_does_not_flag_same_role_in_different_cities_as_duplicates():
    # Same title, near-identical templated body, but two genuinely different,
    # both-applicable openings — must not collapse into one.
    title = "AI Researcher - Post-Training"
    body_template = (
        "Join our research team working on large language model post-training. "
        "You will design and run experiments, collaborate with the core research "
        "group, and help ship improvements that reach production models."
    )
    sig_a = minhash_signature(f"{title}\n{body_template}")
    sig_b = minhash_signature(f"{title}\n{body_template}")
    assert is_near_duplicate(title, sig_a, title, sig_b, "London", "London")
    assert not is_near_duplicate(title, sig_a, title, sig_b, "London", "Bochum")
    # Unknown location on either side should never block a real match.
    assert is_near_duplicate(title, sig_a, title, sig_b, None, "Bochum")
    assert is_near_duplicate(title, sig_a, title, sig_b, "London", None)


def test_minhash_does_not_flag_different_roles_sharing_company_boilerplate():
    # Real-world case that tripped up a body-only check: two different roles
    # at the same company, where identical "who we are" boilerplate sits
    # ahead of the role-specific text and dominates the shingle overlap.
    boilerplate = (
        "Who is Acme? Acme enables organizations to ship software with confidence. "
        "We are trusted by thousands of customers worldwide and have a global team "
        "working across many offices, committed to diversity and inclusion for all."
    )
    title_a = "Account Executive - EMEA East"
    posting_a = f"{title_a}\n{boilerplate} In this role you will own EMEA East accounts."
    title_b = "Account Executive, Spanish and Italian speaker"
    posting_b = (
        f"{title_b}\n{boilerplate} In this role you will support Spanish and Italian clients."
    )

    sig_a = minhash_signature(posting_a)
    sig_b = minhash_signature(posting_b)
    assert not is_near_duplicate(title_a, sig_a, title_b, sig_b)

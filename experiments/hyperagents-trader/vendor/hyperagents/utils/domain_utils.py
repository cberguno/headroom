def get_domain_score_key(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review", "imo_grading"]:
        return "overall_accuracy"
    # Balrog game domains
    elif "balrog" in domain:
        return "average_progress"
    # Genesis robotic control domains
    elif "genesis" in domain:
        return "average_fitness"
    # Polyglot domain
    elif "polyglot" in domain:
        return "accuracy_score"
    # IMO proof domain
    elif domain == "imo_proof":
        return "points_percentage"
    # Alpaca paper-trading domain
    elif domain == "alpaca_trading":
        return "risk_adjusted_score"


def get_domain_splits(domain, eval_test=False):
    # Human preferences domains
    if domain in ["search_arena", "paper_review", "imo_grading"]:
        splits = ["train", "val"]
        if eval_test:
            splits.append("test")
        return splits
    # Balrog game domains
    elif "balrog" in domain:
        return ["train"]
    # Genesis robotic control domains
    elif "genesis" in domain:
        return ["train"]
    # Polyglot domain
    elif "polyglot" in domain:
        return ["train"]
    # IMO Proof domain
    elif domain == "imo_proof":
        return ["train"]
    # Alpaca paper-trading domain: real chronological train/val/test windows
    elif domain == "alpaca_trading":
        splits = ["train", "val"]
        if eval_test:
            splits.append("test")
        return splits


def can_domain_ensembled(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return True
    # Balrog game domains
    elif "balrog" in domain:
        return False
    # Genesis robotic control domains
    elif "genesis" in domain:
        return False
    # Polyglot domain
    elif "polyglot" in domain:
        return False
    # IMO grading domain
    elif domain == "imo_grading":
        return True
    # IMO proof domain
    elif domain == "imo_proof":
        return False
    # Alpaca paper-trading domain: averaging trades across lineages has no
    # clean semantics the way majority-voting human-preference labels does
    elif domain == "alpaca_trading":
        return False


def get_domain_eval_subset(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return "_filtered_100_train"
    # Balrog game domains
    elif "balrog" in domain:
        return ""
    # Genesis robotic control domains
    elif "genesis" in domain:
        return ""
    # Polyglot domain
    elif "polyglot" in domain:
        return ""
    # IMO grading domain
    elif domain == "imo_grading":
        return "_filtered_100_train"
    # IMO proof domain
    elif domain == "imo_proof":
        return ""
    # Alpaca paper-trading domain: "_train" so generate_loop.py's
    # eval_subset.replace("_train", f"_{split}") produces "_val"/"_test",
    # which domains/harness.py's alpaca_trading branch reads as the split
    elif domain == "alpaca_trading":
        return "_train"


def get_domain_test_subset(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return "_filtered_100_test"
    # Balrog game domains
    elif "balrog" in domain:
        return ""
    # Genesis robotic control domains
    elif "genesis" in domain:
        return ""
    # Polyglot domain
    elif "polyglot" in domain:
        return ""
    # IMO grading domain
    elif domain == "imo_grading":
        return "_filtered_100_test"
    # IMO proof domain
    elif domain == "imo_proof":
        return ""
    # Alpaca paper-trading domain
    elif domain == "alpaca_trading":
        return "_test"


def get_domain_stagedeval_samples(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return 10
    # Balrog game domains
    elif "balrog" in domain:
        return 1
    # Genesis robotic control domains
    elif "genesis" in domain:
        return 3
    # Polyglot domain
    elif "polyglot" in domain:
        return 10
    # IMO grading domain
    elif domain == "imo_grading":
        return 10
    # IMO proof domain
    elif domain == "imo_proof":
        return 10
    # Alpaca paper-trading domain: 10 trading days for a quick staged eval
    elif domain == "alpaca_trading":
        return 10


def get_domain_stagedeval_frac(domain):
    # NOTE: this is hardcoded wrt get_domain_stagedeval_samples and default domain configs
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return 10/100
    # Balrog game domains
    elif "balrog_babyai" in domain:
        return 1/10
    elif "balrog_minihack" in domain:
        return 1/5
    # Genesis robotic control domains
    elif "genesis" in domain:
        return 3/6
    # Polyglot domain
    elif "polyglot" in domain:
        return 10/60
    # IMO grading domain
    elif domain == "imo_grading":
        return 10/100
    # IMO proof domain
    elif domain == "imo_proof":
        return 10/60
    # Alpaca paper-trading domain: 10 of the 180 real trading days in train
    elif domain == "alpaca_trading":
        return 10/180


def has_domain_val_subset(domain):
    # Human preferences domains
    if domain in ["search_arena", "paper_review"]:
        return True
    # Balrog game domains
    elif "balrog" in domain:
        return False
    # Genesis robotic control domains
    elif "genesis" in domain:
        return False
    # Polyglot domain
    elif "polyglot" in domain:
        return False
    # IMO grading domain
    elif domain == "imo_grading":
        return True
    # IMO proof domain
    elif domain == "imo_proof":
        return False
    # Alpaca paper-trading domain
    elif domain == "alpaca_trading":
        return True

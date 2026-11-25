"""The deterministic risk score (0-100) for a hub, with a breakdown.

For each of the five categories:
    nri_score      = the worst NRI hazard in the category, by frequency
                     national percentile (0-100)
    observed_score = observed yearly metric on a fixed 0-100 scale
                     (chronic categories only: winter, heat, flood)
    score          = 70% nri_score + 30% observed_score   (chronic)
                   = nri_score                            (acute)
Overall score = weighted sum of the category scores.

All weights and scales live in app/scoring_config.py.

Run `python -m app.scoring` to print the ranking of all hubs.
"""

from app import cache, metrics, nri
from app import scoring_config as config
from app.hubs import load_hubs


def nri_category_score(category, nri_hazards):
    """The worst (max) NRI frequency percentile among the category's hazards.

    Returns the score and the hazard it came from. Hazards that do not happen
    in the county (e.g. hurricane in Denver) have percentile 0.
    """
    worst_hazard, worst_score = None, 0.0
    for hazard in config.CATEGORY_HAZARDS[category]:
        score = nri_hazards[hazard]["frequency_percentile"]
        if score > worst_score:
            worst_hazard, worst_score = hazard, score
    return worst_score, worst_hazard


def observed_category_score(category, hub_metrics):
    """Observed metric on a 0-100 scale, or None for acute categories."""
    scale = config.OBSERVED_SCALES.get(category)
    if scale is None:
        return None
    value = hub_metrics[scale["metric"]]
    return min(100.0, 100.0 * value / scale["full_score_at"])


def category_score(category, nri_hazards, hub_metrics):
    """Score one category, with every number that went into it."""
    nri_score, worst_hazard = nri_category_score(category, nri_hazards)
    observed_score = observed_category_score(category, hub_metrics)

    if observed_score is None:
        score = nri_score
    else:
        score = (config.NRI_SHARE * nri_score
                 + config.OBSERVED_SHARE * observed_score)

    result = {
        "score": round(score, 1),
        "nri_score": round(nri_score, 1),
        "worst_nri_hazard": worst_hazard,
        "observed_score": None,
        "observed_metric": None,
        "observed_value": None,
    }
    if observed_score is not None:
        metric = config.OBSERVED_SCALES[category]["metric"]
        result.update(observed_score=round(observed_score, 1),
                      observed_metric=metric,
                      observed_value=hub_metrics[metric])
    return result


def risk_score(nri_risk, hub_metrics):
    """Overall score plus the breakdown per category.

    nri_risk:    output of nri.fetch_county_risk
    hub_metrics: output of metrics.compute_metrics (5-year period)
    """
    categories = {
        category: category_score(category, nri_risk["hazards"], hub_metrics)
        for category in config.CATEGORY_HAZARDS
    }
    overall = sum(config.CATEGORY_WEIGHTS[category] * result["score"]
                  for category, result in categories.items())
    return {"overall": round(overall, 1), "categories": categories}


def score_hub(hub, db_path=cache.DB_PATH):
    """Fetch the data for one hub and score it."""
    nri_risk = nri.fetch_county_risk(hub["county_fips"], db_path)
    hub_metrics = metrics.get_hub_metrics(hub, db_path=db_path)
    return {
        "hub_id": hub["id"],
        "name": hub["name"],
        "region": hub["region"],
        **risk_score(nri_risk, hub_metrics),
        "metrics": hub_metrics,
        "nri_version": nri_risk["nri_version"],
    }


def rank(scored_hubs, category=None):
    """Sort scored hubs, highest risk first: by overall score, or by one category."""
    if category is None:
        return sorted(scored_hubs, key=lambda h: h["overall"], reverse=True)
    return sorted(scored_hubs, key=lambda h: h["categories"][category]["score"],
                  reverse=True)


if __name__ == "__main__":
    scored = [score_hub(hub) for hub in load_hubs()]
    names = list(config.CATEGORY_HAZARDS)
    print(f"{'hub':<20}{'overall':>8}" + "".join(f"{n:>14}" for n in names))
    for hub in rank(scored):
        row = "".join(f"{hub['categories'][n]['score']:>14}" for n in names)
        print(f"{hub['name']:<20}{hub['overall']:>8}{row}")

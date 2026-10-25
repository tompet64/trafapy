"""Regression tests using captured API structures, plus defensive error cases.

Direct access includes recursive search within its response. It must not be
confused with the separate hierarchical fallback. See fixtures/structure/README.md.
"""

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from trafapy.client import TrafikanalysClient


PRODUCT = "t10011"
FIXTURES = Path(__file__).parent / "fixtures" / "structure"


def load_structure(variable=None):
    suffix = "-" + variable if variable else ""
    return json.loads((FIXTURES / (PRODUCT + suffix + ".json")).read_text(encoding="utf-8"))


@pytest.fixture
def client_no_cache(tmp_path, monkeypatch):
    """Isolate cache and fail immediately on accidental network access."""
    def unexpected_network(*args, **kwargs):
        pytest.fail("Captured-response tests must not access the network")

    monkeypatch.setattr("requests.sessions.Session.request", unexpected_network)
    return TrafikanalysClient(
        cache_enabled=False,
        cache_dir=str(tmp_path),
        rate_limit_enabled=False,
    )


def install_direct_response(monkeypatch, client, response):
    request = Mock(return_value=response)
    fallback = Mock(side_effect=AssertionError("Direct lookup must not use the fallback"))
    monkeypatch.setattr(client, "_make_request", request)
    monkeypatch.setattr(client, "_explore_variable_options_hierarchical", fallback)
    return request, fallback


def test_product_variables_follow_parent_name_and_preserve_hierarchy(
    client_no_cache, monkeypatch, captured_bus_structure
):
    response = captured_bus_structure
    product = next(item for item in response["StructureItems"] if item["Name"] == PRODUCT)
    assert product["StructureItems"] == []
    # A realistic sibling from another product must not leak into the result.
    response["StructureItems"].append({
        "Type": "D", "Name": "unrelated", "ParentName": "other-product",
        "StructureItems": [],
    })
    request = Mock(return_value=response)
    monkeypatch.setattr(client_no_cache, "_make_request", request)

    result = client_no_cache.explore_product_variables(PRODUCT)

    assert result["name"].tolist() == [
        "ar", "avregform", "dimpo", "leasing", "bussklass", "drivm", "pass",
        "itrfslut", "avstslut", "nyregunder", "avregunder", "agare", "agarkat", "tillst",
    ]
    rows = result.set_index("name")
    assert rows["type"].to_dict() == {
        **{name: "Variable" for name in [
            "ar", "avregform", "dimpo", "leasing", "bussklass", "drivm", "pass",
            "agarkat", "tillst",
        ]},
        **{name: "Measure" for name in ["itrfslut", "avstslut", "nyregunder", "avregunder"]},
        "agare": "Hierarchy",
    }
    assert rows.loc["agarkat", "parent_hierarchy"] == "agare"
    assert rows.loc["tillst", "parent_hierarchy"] == "agare"
    assert pd.isna(rows.loc["ar", "parent_hierarchy"])
    assert pd.isna(rows.loc["agare", "parent_hierarchy"])
    assert rows.loc["agarkat", "label"] == "Ägarkategori"
    assert rows.loc["agarkat", "has_filter_options"]
    assert not rows.loc["agare", "has_filter_options"]
    assert not rows.loc["itrfslut", "has_filter_options"]
    request.assert_called_once_with(
        client_no_cache.BASE_URL + "/structure", {"query": PRODUCT, "lang": "sv"}
    )


@pytest.mark.parametrize(
    "variable, expected",
    [
        ("ar", [
            {"name": "senaste", "label": "Senaste", "description": None,
             "option_type": "Filter", "unique_id": "DarDVsenaste"},
            {"name": "forra", "label": "Föregående", "description": None,
             "option_type": "Filter", "unique_id": "DarDVforra"},
        ] + [
            {"name": str(year), "label": str(year), "description": "",
             "option_type": "Value", "unique_id": "DarDV" + str(year)}
            for year in range(2001, 2026)
        ]),
        ("agarkat", [
            {"name": code, "label": label, "description": "",
             "option_type": "Value", "unique_id": "DagarkatDV" + code}
            for code, label in [("10", "Fysisk person"), ("20", "Juridisk person"), ("t1", "Totalt")]
        ]),
        ("tillst", [
            {"name": code, "label": label, "description": "",
             "option_type": "Value", "unique_id": "DtillstDV" + code}
            for code, label in [("1", "Yrkesmässig trafik"), ("2", "Firmabilstrafik"), ("t1", "Totalt")]
        ]),
    ],
)
def test_direct_lookup_returns_exact_captured_options_without_fallback(
    client_no_cache, monkeypatch, variable, expected
):
    request, fallback = install_direct_response(
        monkeypatch, client_no_cache, load_structure(variable)
    )

    result = client_no_cache.explore_variable_options(PRODUCT, variable)

    pd.testing.assert_frame_equal(result, pd.DataFrame(expected))
    request.assert_called_once_with(
        client_no_cache.BASE_URL + "/structure",
        {"query": PRODUCT + "|" + variable, "lang": "sv"},
    )
    fallback.assert_not_called()


@pytest.mark.parametrize("children", [[], None])
def test_defensive_present_variable_without_options_does_not_trigger_fallback(
    client_no_cache, monkeypatch, children
):
    """Derived error cases, not additional captured API responses."""
    response = load_structure("ar")
    variable = next(item for item in response["StructureItems"] if item["Name"] == "ar")
    if children is None:
        variable.pop("StructureItems")
    else:
        variable["StructureItems"] = children
    request, fallback = install_direct_response(monkeypatch, client_no_cache, response)

    result = client_no_cache.explore_variable_options(PRODUCT, "ar")

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert request.call_count == 1
    fallback.assert_not_called()


@pytest.mark.parametrize("response", [{}, {"StructureItems": []}, {"StructureItems": [
    {"Type": "P", "Name": PRODUCT, "StructureItems": []},
]}], ids=["missing-structure", "empty-structure", "variable-absent"])
def test_defensive_invalid_direct_response_dispatches_to_fallback(
    client_no_cache, monkeypatch, response
):
    """Verify dispatch only; this does not establish live fallback reachability."""
    request = Mock(return_value=response)
    expected = pd.DataFrame([{"name": "sentinel"}])
    fallback = Mock(return_value=expected)
    monkeypatch.setattr(client_no_cache, "_make_request", request)
    monkeypatch.setattr(client_no_cache, "_explore_variable_options_hierarchical", fallback)

    result = client_no_cache.explore_variable_options(PRODUCT, "agarkat")

    assert result is expected
    assert request.call_count == 1
    fallback.assert_called_once_with(PRODUCT, "agarkat")


def test_defensive_fallback_cannot_build_path_from_captured_flat_product(
    client_no_cache, monkeypatch
):
    """Document its current limitation without claiming the live API uses it."""
    request = Mock(return_value=load_structure())
    monkeypatch.setattr(client_no_cache, "_make_request", request)

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, "agarkat")

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    request.assert_called_once_with(
        client_no_cache.BASE_URL + "/structure", {"query": PRODUCT, "lang": "sv"}
    )

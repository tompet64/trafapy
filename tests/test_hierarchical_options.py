"""Isolated tests for the hierarchical metadata fallback."""

import pandas as pd
import pytest

from trafapy.client import TrafikanalysClient


PRODUCT = "t12345"
VARIABLE = "kommun"


@pytest.fixture
def client_no_cache(tmp_path):
    """Build a client that cannot read or write a persistent cache."""
    return TrafikanalysClient(
        cache_enabled=False,
        cache_dir=str(tmp_path),
        rate_limit_enabled=False,
    )


def structure_with_hierarchy():
    return {
        "StructureItems": [
            {
                "Type": "P",
                "Name": PRODUCT,
                "StructureItems": [
                    {
                        "Type": "H",
                        "Name": "region",
                        "StructureItems": [
                            {
                                "Type": "H",
                                "Name": "län",
                                "StructureItems": [
                                    {"Type": "D", "Name": VARIABLE}
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def install_structure_mocks(monkeypatch, client, initial, hierarchical):
    """Replace both structure reads and return the second response on demand."""
    monkeypatch.setattr(client, "_get_structure", lambda query: initial)
    request = {}

    def fake_cached_request(**kwargs):
        request.update(kwargs)
        return hierarchical

    monkeypatch.setattr("trafapy.client.cached_api_request", fake_cached_request)
    return request


def test_builds_nested_hierarchy_query_and_extracts_values_and_filters(
    client_no_cache, monkeypatch
):
    client_no_cache.debug = True
    response = {
        "StructureItems": [
            {
                "Type": "H",
                "Name": "result-root",
                "StructureItems": [
                    {
                        "Type": "H",
                        "Name": "result-branch",
                        "StructureItems": [
                            {
                                "Type": "D",
                                "Name": VARIABLE,
                                "Label": "Kommun",
                                "StructureItems": [
                                    {"Type": "DV", "Name": "0180", "Label": "Stockholm"},
                                    {
                                        "Type": "F",
                                        "Name": "alla",
                                        "Label": "Samtliga kommuner",
                                        "UniqueId": "filter-1",
                                    },
                                    {"Type": "X", "Name": "ignored", "Label": "Ignored"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    request = install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), response
    )

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert request["url"] == f"{client_no_cache.BASE_URL}/structure"
    assert request["params"] == {
        "query": f"{PRODUCT}|region|län|{VARIABLE}",
        "lang": "sv",
    }
    assert result.to_dict("records") == [
        {
            "name": "0180",
            "label": "Stockholm",
            "description": "",
            "option_type": "Value",
            "unique_id": "",
        },
        {
            "name": "alla",
            "label": "Samtliga kommuner",
            "description": "",
            "option_type": "Filter",
            "unique_id": "filter-1",
        },
    ]


def test_finds_variable_at_top_level_of_hierarchical_response(
    client_no_cache, monkeypatch
):
    response = {
        "StructureItems": [
            {
                "Name": VARIABLE,
                "StructureItems": [{"Type": "DV", "Name": "0180", "Label": "Stockholm"}],
            }
        ]
    }
    install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), response
    )

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert result["name"].tolist() == ["0180"]
    assert result["option_type"].tolist() == ["Value"]


def test_finds_measure_inside_hierarchy(client_no_cache, monkeypatch):
    initial = structure_with_hierarchy()
    initial["StructureItems"][0]["StructureItems"][0]["StructureItems"][0][
        "StructureItems"
    ][0]["Type"] = "M"
    response = {
        "StructureItems": [
            {"Name": VARIABLE, "StructureItems": [{"Type": "DV", "Name": "0180"}]}
        ]
    }
    request = install_structure_mocks(monkeypatch, client_no_cache, initial, response)

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert request["params"]["query"] == f"{PRODUCT}|region|län|{VARIABLE}"
    assert result["name"].tolist() == ["0180"]


@pytest.mark.parametrize(
    "initial",
    [
        {},
        {"StructureItems": []},
        {"StructureItems": [{"Type": "P", "Name": PRODUCT}]},
        {
            "StructureItems": [
                {
                    "Type": "P",
                    "Name": PRODUCT,
                    "StructureItems": [{"Type": "H", "Name": "region", "StructureItems": []}],
                }
            ]
        },
        {
            "StructureItems": [
                {
                    "Type": "P",
                    "Name": PRODUCT,
                    "StructureItems": [
                        {
                            "Type": "H",
                            "Name": "region",
                            "StructureItems": [
                                {"Type": "M", "Name": "different_measure"}
                            ],
                        }
                    ],
                }
            ]
        },
    ],
    ids=[
        "missing-structure-items",
        "empty-structure",
        "product-without-children",
        "empty-hierarchy",
        "hierarchy-without-requested-variable",
    ],
)
def test_returns_empty_without_second_request_when_no_hierarchy_path(
    client_no_cache, monkeypatch, initial
):
    def unexpected_request(**kwargs):
        pytest.fail("A hierarchical API request should not be made without a path")

    monkeypatch.setattr(client_no_cache, "_get_structure", lambda query: initial)
    monkeypatch.setattr("trafapy.client.cached_api_request", unexpected_request)

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"StructureItems": []},
        {
            "StructureItems": [
                {"Name": "other", "StructureItems": [{"Name": "nested-other"}]}
            ]
        },
    ],
    ids=["missing-structure-items", "empty-structure", "variable-not-found-recursively"],
)
def test_returns_empty_when_hierarchical_response_lacks_variable(
    client_no_cache, monkeypatch, response
):
    install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), response
    )

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_variable_without_children_returns_empty_options(client_no_cache, monkeypatch):
    response = {"StructureItems": [{"Name": VARIABLE, "StructureItems": []}]}
    install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), response
    )

    result = client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_debug_messages_cover_hierarchical_fallback_outcomes(
    client_no_cache, monkeypatch, capsys
):
    client_no_cache.debug = True

    monkeypatch.setattr(client_no_cache, "_get_structure", lambda query: {})
    client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    response = {
        "StructureItems": [
            {
                "Name": "result-root",
                "StructureItems": [
                    {"Name": "other", "StructureItems": [{"Name": "nested-other"}]}
                ],
            }
        ]
    }
    install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), response
    )
    client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    install_structure_mocks(
        monkeypatch,
        client_no_cache,
        structure_with_hierarchy(),
        {"StructureItems": [{"Name": VARIABLE, "StructureItems": []}]},
    )
    client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    install_structure_mocks(
        monkeypatch, client_no_cache, structure_with_hierarchy(), {}
    )
    client_no_cache._explore_variable_options_hierarchical(PRODUCT, VARIABLE)

    output = capsys.readouterr().out
    assert "No hierarchy path found" in output
    assert "Using hierarchical query" in output
    assert "Variable kommun not found in hierarchical API response" in output
    assert "No filter options found for this variable" in output
    assert "Found variable in hierarchical response" in output
    assert "No 'StructureItems' in hierarchical API response" in output

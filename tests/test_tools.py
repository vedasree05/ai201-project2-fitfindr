"""
tests/test_tools.py

One test per failure mode for each of the three FitFindr tools.

search_listings  — pure Python logic, no mocking needed
suggest_outfit   — calls Groq; Groq client is mocked so tests run offline
create_fit_card  — calls Groq; Groq client is mocked so tests run offline
"""

from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_item():
    """A minimal listing dict that matches the shape returned by search_listings."""
    return {
        "id": "lst_test",
        "title": "Vintage Graphic Tee",
        "description": "A worn-in 90s band tee.",
        "category": "tops",
        "style_tags": ["vintage", "grunge"],
        "size": "M",
        "condition": "good",
        "price": 22.0,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }


@pytest.fixture
def mock_groq_response():
    """Factory that returns a mock Groq completion with the given text."""
    def _make(text: str):
        message = MagicMock()
        message.content = text
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        return completion
    return _make


# ── Tool 1: search_listings ───────────────────────────────────────────────────

class TestSearchListings:
    def test_no_keyword_match_returns_empty_list(self):
        """Failure mode: description has zero overlap with any listing."""
        results = search_listings("xyzzy frobnicator")
        assert results == []

    def test_price_filter_eliminates_all(self):
        """Failure mode: max_price is so low that every listing is filtered out."""
        results = search_listings("vintage", max_price=0.01)
        assert results == []

    def test_size_filter_eliminates_all(self):
        """Failure mode: size string matches nothing in the dataset."""
        results = search_listings("vintage", size="ZZZZ")
        assert results == []

    def test_returns_empty_list_not_exception(self):
        """search_listings must never raise — always returns a list."""
        results = search_listings("designer ballgown", size="XXS", max_price=1.0)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_results_sorted_by_relevance(self):
        """Items with more keyword matches should appear before weaker matches."""
        # "vintage grunge" should score higher for items tagged both vs. just one
        results = search_listings("vintage grunge")
        assert len(results) >= 2
        # Confirm order: each result scores >= the next (non-strict to allow ties)
        scores = []
        for item in results:
            text = " ".join([item["title"], item["description"], " ".join(item["style_tags"])]).lower()
            score = sum(1 for kw in ["vintage", "grunge"] if kw in text)
            scores.append(score)
        assert scores == sorted(scores, reverse=True)

    def test_size_match_is_case_insensitive_and_substring(self):
        """'m' should match listings sized 'M', 'S/M', 'M/L'."""
        results = search_listings("tee", size="m")
        assert all("m" in item["size"].lower() for item in results)

    def test_each_result_has_required_fields(self):
        """Every returned dict must contain all 11 listing fields."""
        required = {"id", "title", "description", "category", "style_tags",
                    "size", "condition", "price", "colors", "brand", "platform"}
        results = search_listings("vintage")
        assert results, "Expected at least one result for 'vintage'"
        for item in results:
            assert required.issubset(item.keys()), f"Missing fields in {item['id']}"


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

class TestSuggestOutfit:
    def test_empty_wardrobe_returns_nonempty_string(self, sample_item, mock_groq_response):
        """Failure mode: wardrobe is empty — must still return a suggestion, not ''."""
        fake_reply = "Try pairing it with wide-leg trousers and chunky boots."
        with patch("tools._get_groq_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                mock_groq_response(fake_reply)
            )
            result = suggest_outfit(sample_item, {"items": []})

        assert isinstance(result, str)
        assert result.strip() != ""

    def test_empty_wardrobe_does_not_raise(self, sample_item, mock_groq_response):
        """Failure mode: empty wardrobe must not raise any exception."""
        with patch("tools._get_groq_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                mock_groq_response("General style advice here.")
            )
            try:
                suggest_outfit(sample_item, {"items": []})
            except Exception as exc:
                pytest.fail(f"suggest_outfit raised on empty wardrobe: {exc}")

    def test_nonempty_wardrobe_returns_string(self, sample_item, mock_groq_response):
        """Happy path: wardrobe with items returns a non-empty outfit string."""
        wardrobe = {"items": [{"name": "baggy jeans"}, {"name": "chunky sneakers"}]}
        fake_reply = "Outfit 1: Tuck the tee into the baggy jeans with chunky sneakers."
        with patch("tools._get_groq_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                mock_groq_response(fake_reply)
            )
            result = suggest_outfit(sample_item, wardrobe)

        assert isinstance(result, str)
        assert result.strip() != ""

    def test_nonempty_wardrobe_prompt_includes_item_names(self, sample_item, mock_groq_response):
        """Wardrobe item names should appear in the prompt sent to the LLM."""
        wardrobe = {"items": [{"name": "pleated trousers"}, {"name": "loafers"}]}
        with patch("tools._get_groq_client") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_groq_response("Outfit here.")
            suggest_outfit(sample_item, wardrobe)

            call_args = instance.chat.completions.create.call_args
            prompt_text = call_args.kwargs["messages"][0]["content"]

        assert "pleated trousers" in prompt_text
        assert "loafers" in prompt_text


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

class TestCreateFitCard:
    def test_empty_outfit_returns_error_string(self, sample_item):
        """Failure mode: empty outfit string → error message, no LLM call, no exception."""
        result = create_fit_card("", sample_item)
        assert isinstance(result, str)
        assert "empty" in result.lower() or "could not" in result.lower()

    def test_whitespace_outfit_returns_error_string(self, sample_item):
        """Failure mode: whitespace-only outfit string is treated the same as empty."""
        result = create_fit_card("   \n\t  ", sample_item)
        assert isinstance(result, str)
        assert "empty" in result.lower() or "could not" in result.lower()

    def test_empty_outfit_does_not_call_llm(self, sample_item):
        """Failure mode: empty outfit must short-circuit before reaching Groq."""
        with patch("tools._get_groq_client") as mock_client:
            create_fit_card("", sample_item)
            mock_client.assert_not_called()

    def test_happy_path_returns_nonempty_string(self, sample_item, mock_groq_response):
        """Happy path: valid outfit string returns a non-empty caption."""
        fake_caption = "thrifted this Vintage Graphic Tee on depop for $22 and it's perfect."
        with patch("tools._get_groq_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                mock_groq_response(fake_caption)
            )
            result = create_fit_card("Tuck it into baggy jeans with chunky sneakers.", sample_item)

        assert isinstance(result, str)
        assert result.strip() != ""

    def test_prompt_includes_item_name_price_platform(self, sample_item, mock_groq_response):
        """Item title, price, and platform must all appear in the prompt."""
        with patch("tools._get_groq_client") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_groq_response("Caption.")
            create_fit_card("Outfit description here.", sample_item)

            call_args = instance.chat.completions.create.call_args
            prompt_text = call_args.kwargs["messages"][0]["content"]

        assert sample_item["title"] in prompt_text
        assert str(sample_item["price"]) in prompt_text
        assert sample_item["platform"] in prompt_text

    def test_uses_high_temperature(self, sample_item, mock_groq_response):
        """LLM must be called with temperature >= 0.9 for varied output."""
        with patch("tools._get_groq_client") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_groq_response("Caption.")
            create_fit_card("Outfit here.", sample_item)

            call_args = instance.chat.completions.create.call_args
            temperature = call_args.kwargs["temperature"]

        assert temperature >= 0.9

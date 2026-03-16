from app.routers.feed import build_mixed_feed


def test_build_mixed_feed_is_deterministic_with_seed():
    items = (
        [{"id": f"p{i}", "type": "profile"} for i in range(6)] +
        [{"id": f"c{i}", "type": "cafeteria"} for i in range(6)] +
        [{"id": f"post{i}", "type": "post"} for i in range(6)]
    )

    weights = {"profile": 2, "cafeteria": 1, "post": 1}

    feed1 = build_mixed_feed(items, page_size=10, weights=weights, max_streak=2, seed=123)
    feed2 = build_mixed_feed(items, page_size=10, weights=weights, max_streak=2, seed=123)

    assert feed1 == feed2
    assert len(feed1) == 10
    assert all("type" in x for x in feed1)


def test_build_mixed_feed_respects_max_streak_when_alternatives_exist():
    # Plenty of alternatives so it shouldn't need to "relax" streak rule
    items = (
        [{"id": f"p{i}", "type": "profile"} for i in range(10)] +
        [{"id": f"c{i}", "type": "cafeteria"} for i in range(10)] +
        [{"id": f"post{i}", "type": "post"} for i in range(10)]
    )

    weights = {"profile": 3, "cafeteria": 2, "post": 2}
    max_streak = 2

    feed = build_mixed_feed(items, page_size=25, weights=weights, max_streak=max_streak, seed=999)

    # Check no more than 2 consecutive same "type"
    streak = 1
    for i in range(1, len(feed)):
        if feed[i]["type"] == feed[i - 1]["type"]:
            streak += 1
            assert streak <= max_streak
        else:
            streak = 1
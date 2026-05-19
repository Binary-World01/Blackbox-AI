from agent import run_optimization


def test_three_generation_loop() -> None:
    result = run_optimization("mTSLA", "make it conservative and reduce drawdown", 3)
    assert result["provider"] == "groq"
    assert len(result["generations"]) == 3
    assert result["latest"]["metrics"]["roi"] > -20
    assert result["latest"]["metrics"]["drawdown"] >= 0
    assert result["memoryNodes"]
    assert result["cascadeMetrics"]["savingsPct"] > 90


if __name__ == "__main__":
    test_three_generation_loop()
    print("Backtest loop verification passed")

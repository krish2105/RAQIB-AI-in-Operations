import pytest

from raqib_api.workforce import staffing_plan


def test_toy_three_slot_problem_matches_hand_solution():
    # mu = 3/h per till, max_rho 0.85 -> tills >= lam/(2.55): [2->1, 5->2 (1.96), 8->4 (3.14)]
    plan = staffing_plan([2, 5, 8], mu=3, max_rho=0.85, max_tills=6, slot_minutes=60)
    assert plan.tills == [1, 2, 4]
    assert all(r <= 0.85 + 1e-9 for r in plan.rho)
    assert plan.staff_hours == 7.0 and plan.baseline_staff_hours == 18.0 and plan.savings_hours == 11.0
    assert plan.wq_min[0] is not None


def test_zero_demand_slots_keep_one_till_open():
    plan = staffing_plan([0, 0, 40], mu=30, max_rho=0.85, max_tills=3)
    assert plan.tills == [1, 1, 2]


def test_infeasible_when_demand_exceeds_capacity():
    with pytest.raises(RuntimeError, match="infeasible"):
        staffing_plan([500], mu=30, max_rho=0.85, max_tills=3)


def test_max_step_smooths_adjacent_slots():
    plan = staffing_plan([0, 0, 200], mu=30, max_rho=0.85, max_tills=10, max_step=2)
    assert plan.tills[2] == 8 and plan.tills[1] >= 6 and plan.tills[0] >= 4


def test_bad_inputs():
    with pytest.raises(ValueError):
        staffing_plan([], mu=30)
    with pytest.raises(ValueError):
        staffing_plan([1], mu=0)

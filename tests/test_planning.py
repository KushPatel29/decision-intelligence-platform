import pandas as pd
import pytest
from decision_platform.planning import zone_summary,plan_capacity


def test_utilization_weights_unequal_capacity_cells():
    capacity=pd.DataFrame({"zone_id":[0,0],"period":["Peak","Off-peak"],
        "baseline_forecast":[90.,10.],"allocated_trips":[5.,0.],"reserve_trips":[0.,0.],
        "capacity_trips":[100.,1000.],"remaining_with_reserve":[5.,990.]})
    row=zone_summary(capacity).loc[0]
    assert row.utilization==pytest.approx(105/1100)
    assert row.remaining_with_reserve==995


def test_new_plan_replaces_saved_trips_and_uses_selected_reserve():
    capacity=pd.DataFrame({"zone_id":[0,0],"period":["Peak","Off-peak"],
        "baseline_forecast":[40.,20.],"allocated_trips":[20.,15.],"reserve_trips":[8.,4.],
        "capacity_trips":[100.,80.],"remaining_with_reserve":[32.,41.]})
    selected=pd.DataFrame({"zone_id":[0,0],"period":["Off-peak","Off-peak"],"incremental_trips":[3.,2.]})
    original=capacity.copy(deep=True)
    result=plan_capacity(capacity,selected,.5).set_index("period")
    assert result.loc["Peak","allocated_trips"]==0
    assert result.loc["Off-peak","allocated_trips"]==5
    assert result.loc["Peak","remaining_with_reserve"]==40
    assert result.loc["Off-peak","remaining_with_reserve"]==45
    assert result.loc["Off-peak","final_utilization"]==pytest.approx(25/80)
    pd.testing.assert_frame_equal(capacity,original)


def test_empty_campaign_keeps_full_baseline_headroom():
    capacity=pd.DataFrame({"zone_id":[1],"period":["Peak"],"baseline_forecast":[60.],
        "allocated_trips":[10.],"reserve_trips":[12.],"capacity_trips":[100.],"remaining_with_reserve":[18.]})
    selected=pd.DataFrame(columns=["zone_id","period","incremental_trips"])
    result=plan_capacity(capacity,selected,.25).iloc[0]
    assert result.allocated_trips==0
    assert result.reserve_trips==15
    assert result.remaining_with_reserve==25
    assert result.final_utilization==.6

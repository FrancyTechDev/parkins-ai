from baseline import recompute_baseline
from aggregate import recompute_daily, recompute_weekly, recompute_monthly

recompute_baseline()
recompute_daily(7)
recompute_weekly()
recompute_monthly()
print("Agg ok")
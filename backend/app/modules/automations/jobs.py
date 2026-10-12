from datetime import timedelta

from app.modules.automations.engine import run_date_rules
from app.platform.jobs.scheduler import scheduled

scheduled("automations.date_rules", every=timedelta(hours=1))(run_date_rules)

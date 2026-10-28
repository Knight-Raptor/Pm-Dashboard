import frappe
from frappe.utils import get_last_day


# ---------------------------------------------------------------- helpers

def _run(errors, key, query, values=None):
    try:
        return frappe.db.sql(query, values or {}, as_dict=True)
    except Exception as e:
        errors[key] = str(e)
        frappe.log_error(title="PM Dashboard: " + key, message=str(e))
        return []


def _unit_filters(building="", block_number="", prop=""):
    sql = ""
    values = {}
    if building:
        sql += " AND u.building = %(building)s"
        values["building"] = building
    if block_number:
        sql += " AND u.block_number = %(block_number)s"
        values["block_number"] = block_number
    if prop:
        sql += " AND u.name = %(prop)s"
        values["prop"] = prop
    return sql, values


def _range(col, key, from_date, to_date, month=False):
    # month=True: whole months, from the 1st of the From month to the last day of the To month
    sql = ""
    values = {}
    if from_date:
        values[key + "_from"] = (from_date[:7] + "-01") if month else from_date
        sql += " AND " + col + " >= %(" + key + "_from)s"
    if to_date:
        values[key + "_to"] = str(get_last_day(to_date)) if month else to_date
        sql += " AND " + col + " <= %(" + key + "_to)s"
    return sql, values


# ---------------------------------------------------------------- overview

_UNITS = """
    SELECT
        u.name AS unit,
        u.building AS building,
        u.block_number AS block_number,
        COALESCE(b.building_name, u.building) AS property_name,
        CASE WHEN EXISTS (
            SELECT 1 FROM `tabRent Contract` rc
            WHERE rc.property = u.name AND rc.docstatus = 1
              AND rc.contract_end_date2 >= CURDATE()
              AND rc.status IN ('Occupied', 'Pre-Booked')
        ) OR u.status = 'Rented' THEN 1 ELSE 0 END AS is_occupied
    FROM `tabProperty` u
    LEFT JOIN `tabBuilding` b ON b.name = u.building
    WHERE 1=1 """


def _overview(errors, building="", block_number="", prop=""):
    where, values = _unit_filters(building, block_number, prop)
    units = _UNITS + where

    summary = _run(errors, "summary", """
        SELECT
            COUNT(DISTINCT property_name) AS total_properties,
            COUNT(DISTINCT building) AS total_buildings,
            COUNT(DISTINCT CASE WHEN COALESCE(block_number, '') <> ''
                  THEN CONCAT(COALESCE(building, ''), '|', block_number) END) AS total_blocks,
            COUNT(*) AS total_units,
            COALESCE(SUM(is_occupied), 0) AS occupied_units,
            COUNT(*) - COALESCE(SUM(is_occupied), 0) AS vacant_units,
            ROUND(100 * COALESCE(SUM(is_occupied), 0) / NULLIF(COUNT(*), 0), 2) AS occupancy_rate
        FROM (""" + units + """) t
    """, values)

    by_property = _run(errors, "by_property", """
        SELECT
            property_name,
            COUNT(*) AS total_units,
            COALESCE(SUM(is_occupied), 0) AS occupied_units,
            COUNT(*) - COALESCE(SUM(is_occupied), 0) AS vacant_units,
            ROUND(100 * COALESCE(SUM(is_occupied), 0) / NULLIF(COUNT(*), 0), 2) AS occupancy_rate
        FROM (""" + units + """) t
        GROUP BY property_name
        ORDER BY property_name
    """, values)

    # TODO: alerts still read the view, so they ignore the filters (Lease step)
    alerts = _run(errors, "alerts", """
        SELECT alert_type, `count` AS alert_count FROM view_pm_alerts
    """)

    return {
        "summary": summary[0] if summary else {},
        "alerts": alerts,
        "by_property": by_property,
    }


# ---------------------------------------------------------------- vacancy

_VACANT_UNITS = """
    SELECT
        u.name AS unit,
        COALESCE(b.building_name, u.building) AS property_name,
        COALESCE(NULLIF(u.rent, 0),
            (SELECT rc3.final_rent_amount FROM `tabRent Contract` rc3
             WHERE rc3.property = u.name AND rc3.docstatus = 1
             ORDER BY rc3.contract_end_date2 DESC LIMIT 1), 0) AS est_rent,
        DATEDIFF(CURDATE(), COALESCE(
            (SELECT MAX(rc2.contract_end_date2) FROM `tabRent Contract` rc2
             WHERE rc2.property = u.name AND rc2.docstatus = 1
               AND rc2.contract_end_date2 < CURDATE()),
            DATE(u.modified))) AS days_vacant
    FROM `tabProperty` u
    LEFT JOIN `tabBuilding` b ON b.name = u.building
    WHERE u.status <> 'Rented'
      AND NOT EXISTS (
        SELECT 1 FROM `tabRent Contract` rc
        WHERE rc.property = u.name AND rc.docstatus = 1
          AND rc.contract_end_date2 >= CURDATE()
          AND rc.status IN ('Occupied', 'Pre-Booked'))
"""


def _rank(rows, entity_type):
    rows = sorted(rows, key=lambda r: -float(r.metric_value or 0))
    total = len(rows)
    for i, r in enumerate(rows):
        n = i + 1
        r["entity_type"] = entity_type
        r["rank_group"] = "top" if n <= 5 else ("bottom" if n > total - 5 else None)
    return rows


def _vacancy(errors, building="", block_number="", prop=""):
    where, values = _unit_filters(building, block_number, prop)
    vacant = _VACANT_UNITS + where

    by_property = _run(errors, "vacancy", """
        SELECT property_name,
               COUNT(*) AS vacant_units,
               ROUND(COALESCE(SUM(est_rent), 0), 2) AS revenue_loss
        FROM (""" + vacant + """) t
        GROUP BY property_name
        ORDER BY revenue_loss DESC
    """, values)

    buckets = _run(errors, "duration", """
        SELECT CASE WHEN days_vacant <= 30 THEN '0-30 days'
                    WHEN days_vacant <= 60 THEN '31-60 days'
                    ELSE '60+ days' END AS bucket,
               COUNT(*) AS units
        FROM (""" + vacant + """) t
        GROUP BY bucket
    """, values)
    counts = {}
    for b in buckets:
        counts[b.bucket] = b.units
    duration = [{"bucket": k, "units": counts.get(k, 0)}
                for k in ["0-30 days", "31-60 days", "60+ days"]]

    props = _run(errors, "top_props", """
        SELECT COALESCE(b.building_name, u.building) AS entity_name,
               COALESCE(SUM(CASE WHEN rc.status IN ('Occupied', 'Pre-Booked')
                                  AND rc.contract_end_date2 >= CURDATE()
                                 THEN rc.monthly_payable_amount ELSE 0 END), 0) AS metric_value,
               COUNT(DISTINCT u.name) AS unit_count
        FROM `tabProperty` u
        LEFT JOIN `tabBuilding` b ON b.name = u.building
        LEFT JOIN `tabRent Contract` rc ON rc.property = u.name AND rc.docstatus = 1
        WHERE 1=1 """ + where + """
        GROUP BY COALESCE(b.building_name, u.building)
    """, values)

    tenants = _run(errors, "bottom_tenants", """
        SELECT COALESCE(c.customer_name, rc.tenant) AS entity_name,
               COALESCE(SUM(CASE WHEN si.docstatus = 1 THEN si.grand_total ELSE 0 END), 0) AS metric_value,
               COUNT(DISTINCT u.name) AS unit_count
        FROM `tabRent Contract` rc
        JOIN `tabProperty` u ON u.name = rc.property
        LEFT JOIN `tabCustomer` c ON c.name = rc.tenant
        LEFT JOIN `tabSales Invoice` si ON si.rent_contract = rc.name
        WHERE rc.docstatus = 1 """ + where + """
        GROUP BY COALESCE(c.customer_name, rc.tenant)
    """, values)

    return {
        "vacancy": by_property,
        "duration": duration,
        "performance": _rank(props, "property") + _rank(tenants, "tenant"),
    }


# ---------------------------------------------------------------- revenue

def _blank_month(period_month):
    return {
        "period_month": period_month,
        "revenue_amount": 0.0,
        "outstanding_rent": 0.0,
        "rent_due": 0.0,
        "rent_outstanding": 0.0,
        "collected_amount": 0.0,
    }


def _revenue(errors, from_date, to_date, building="", block_number="", prop=""):
    unit_sql, values = _unit_filters(building, block_number, prop)
    inv_sql, v1 = _range("si.posting_date", "m", from_date, to_date, month=True)
    pay_sql, v2 = _range("pe.posting_date", "m", from_date, to_date, month=True)
    ex_sql, v3 = _range("rc.contract_end_date2", "d", from_date, to_date)
    values.update(v1)
    values.update(v2)
    values.update(v3)

    rent_case = """COALESCE(si.is_damage_invoice, 0) = 0
                   AND COALESCE(si.is_deposite_invoice, 0) = 0
                   AND si.is_property_invoice = 1"""

    invoices = _run(errors, "invoices", """
        SELECT
            CONCAT(LEFT(si.posting_date, 7), '-01') AS period_month,
            SUM(si.grand_total) AS revenue_amount,
            SUM(si.outstanding_amount) AS outstanding_rent,
            SUM(CASE WHEN """ + rent_case + """ THEN si.grand_total ELSE 0 END) AS rent_due,
            SUM(CASE WHEN """ + rent_case + """ THEN si.outstanding_amount ELSE 0 END) AS rent_outstanding
        FROM `tabSales Invoice` si
        JOIN `tabRent Contract` rc ON rc.name = si.rent_contract
        JOIN `tabProperty` u ON u.name = rc.property
        WHERE si.docstatus = 1 AND COALESCE(si.rent_contract, '') <> ''
        """ + unit_sql + inv_sql + """
        GROUP BY CONCAT(LEFT(si.posting_date, 7), '-01')
    """, values)

    payments = _run(errors, "payments", """
        SELECT
            CONCAT(LEFT(pe.posting_date, 7), '-01') AS period_month,
            SUM(pe.paid_amount) AS collected_amount
        FROM `tabPayment Entry` pe
        JOIN `tabRent Contract` rc ON rc.name = pe.rent_contract
        JOIN `tabProperty` u ON u.name = rc.property
        WHERE pe.docstatus = 1 AND COALESCE(pe.mode_of_payment, '') <> 'PDC'
          AND COALESCE(pe.rent_contract, '') <> ''
        """ + unit_sql + pay_sql + """
        GROUP BY CONCAT(LEFT(pe.posting_date, 7), '-01')
    """, values)

    months = {}
    for r in invoices:
        m = _blank_month(r.period_month)
        m["revenue_amount"] = float(r.revenue_amount or 0)
        m["outstanding_rent"] = float(r.outstanding_rent or 0)
        m["rent_due"] = float(r.rent_due or 0)
        m["rent_outstanding"] = float(r.rent_outstanding or 0)
        months[r.period_month] = m
    for r in payments:
        if r.period_month not in months:
            months[r.period_month] = _blank_month(r.period_month)
        months[r.period_month]["collected_amount"] = float(r.collected_amount or 0)
    monthly = [months[k] for k in sorted(months)]

    income = _run(errors, "income", """
        SELECT COALESCE(SUM(rc.final_rent_amount), 0) AS monthly_rental_income
        FROM `tabRent Contract` rc
        JOIN `tabProperty` u ON u.name = rc.property
        WHERE rc.docstatus = 1 AND rc.status IN ('Occupied', 'Pre-Booked')
          AND rc.contract_end_date2 >= CURDATE()
        """ + unit_sql, values)
    monthly_income = float(income[0].monthly_rental_income or 0) if income else 0.0

    latest = monthly[-1] if monthly else _blank_month("")
    kpi = {
        "period_month": latest["period_month"],
        "monthly_rental_income": monthly_income,
        "annual_contract_value": monthly_income * 12,
        "outstanding_rent": latest["outstanding_rent"],
        "collected_amount": latest["collected_amount"],
        "collection_rate": round(100 * latest["collected_amount"] / monthly_income, 2)
        if monthly_income else 0,
    }

    breakdown = _run(errors, "breakdown", """
        SELECT
            CASE WHEN si.is_damage_invoice = 1 THEN 'Damage'
                 WHEN si.is_deposite_invoice = 1 THEN 'Deposit'
                 WHEN si.is_property_invoice = 1 THEN 'Rent'
                 ELSE 'Other' END AS revenue_category,
            SUM(si.grand_total) AS revenue_amount
        FROM `tabSales Invoice` si
        JOIN `tabRent Contract` rc ON rc.name = si.rent_contract
        JOIN `tabProperty` u ON u.name = rc.property
        WHERE si.docstatus = 1 AND COALESCE(si.rent_contract, '') <> ''
        """ + unit_sql + inv_sql + """
        GROUP BY revenue_category
        ORDER BY revenue_amount DESC
    """, values)

    expiries = _run(errors, "expiries", """
        SELECT
            COALESCE(c.customer_name, rc.tenant) AS tenant_name,
            COALESCE(b.building_name, u.building) AS property_name,
            COALESCE(u.apt_no, u.name) AS unit_name,
            rc.contract_end_date2 AS expiry_date,
            DATEDIFF(rc.contract_end_date2, CURDATE()) AS days_to_expiry,
            rc.final_rent_amount AS rent_amount,
            LEFT(rc.contract_end_date2, 7) AS expiry_month
        FROM `tabRent Contract` rc
        JOIN `tabProperty` u ON u.name = rc.property
        LEFT JOIN `tabBuilding` b ON b.name = u.building
        LEFT JOIN `tabCustomer` c ON c.name = rc.tenant
        WHERE rc.docstatus = 1
        """ + unit_sql + ex_sql + """
        ORDER BY days_to_expiry ASC
    """, values)

    calendar = _run(errors, "calendar", """
        SELECT LEFT(rc.contract_end_date2, 7) AS expiry_month, COUNT(*) AS expiry_month_count
        FROM `tabRent Contract` rc
        JOIN `tabProperty` u ON u.name = rc.property
        WHERE rc.docstatus = 1
        """ + unit_sql + ex_sql + """
        GROUP BY LEFT(rc.contract_end_date2, 7)
        ORDER BY expiry_month
    """, values)

    return {
        "kpi": kpi,
        "breakdown": breakdown,
        "trend": monthly,
        "monthly": monthly,
        "expiries": expiries,
        "calendar": calendar,
    }


# ---------------------------------------------------------------- endpoints

@frappe.whitelist()
def get_dashboard(tab="overview", from_date="", to_date="",
                  building="", block_number="", property=""):
    errors = {}
    from_date = from_date or ""
    to_date = to_date or ""
    building = building or ""
    block_number = block_number or ""
    prop = property or ""

    if tab == "vacancy":
        result = _vacancy(errors, building, block_number, prop)
    elif tab == "revenue":
        result = _revenue(errors, from_date, to_date, building, block_number, prop)
    else:
        result = _overview(errors, building, block_number, prop)

    result["errors"] = errors
    return result


@frappe.whitelist()
def get_filter_options(building="", block_number="", property=""):
    v = {"building": building or "", "block_number": block_number or ""}
    by_block = " AND u.block_number = %(block_number)s" if block_number else ""
    by_building = " AND u.building = %(building)s" if building else ""

    buildings = frappe.db.sql(
        "SELECT DISTINCT b.name AS value, COALESCE(b.building_name, b.name) AS label "
        "FROM `tabBuilding` b JOIN `tabProperty` u ON u.building = b.name "
        "WHERE 1=1" + by_block + " ORDER BY label", v, as_dict=True)

    blocks = frappe.db.sql(
        "SELECT DISTINCT u.block_number AS value FROM `tabProperty` u "
        "WHERE COALESCE(u.block_number, '') <> ''" + by_building +
        " ORDER BY u.block_number", v, as_dict=True)

    properties = frappe.db.sql(
        "SELECT u.name AS value, COALESCE(u.apt_no, u.name) AS label FROM `tabProperty` u "
        "WHERE 1=1" + by_building + by_block + " ORDER BY label", v, as_dict=True)

    return {"buildings": buildings, "blocks": blocks, "properties": properties}
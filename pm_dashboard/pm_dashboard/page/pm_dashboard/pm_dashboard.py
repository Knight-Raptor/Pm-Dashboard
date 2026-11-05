"""Read-only data providers for the PM Dashboard page.

One provider per KPI drives both the card value and its drill-down dialog so
every displayed figure can be traced back to the underlying documents.
"""

from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate


COMPANY = "Al Safat Invest"
RENTAL_INCOME_ACCOUNT = "Rental income - ASI"
PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100
LIST_LIMIT = 50000


def _date(value):
    if not value:
        return None
    return getdate(value)


def _iso(value):
    return value.isoformat() if value else ""


def _money(value):
    return round(flt(value), 2)


def _month_end(value):
    month_start = getdate(value).replace(day=1)
    return add_days(add_months(month_start, 1), -1)


def _months_between(start, end):
    months = []
    current = getdate(start).replace(day=1)
    end = getdate(end)
    while current <= end:
        months.append(current)
        current = add_months(current, 1)
    return months


def prorated_monthly(amount, start, end, window_start, window_end):
    """Prorate monthly rent across actual days in each calendar month."""
    if not start or not end or not window_start or not window_end:
        return 0.0
    start = max(getdate(start), getdate(window_start))
    end = min(getdate(end), getdate(window_end))
    if start > end:
        return 0.0
    total = 0.0
    current = start
    while current <= end:
        month_end = _month_end(current)
        segment_end = min(month_end, end)
        days = (segment_end - current).days + 1
        total += flt(amount) * days / month_end.day
        current = add_days(segment_end, 1)
    return total


def _page_args(page, page_size):
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(page_size or PAGE_SIZE_DEFAULT)
    except (TypeError, ValueError):
        page_size = PAGE_SIZE_DEFAULT
    return page, min(max(page_size, 1), PAGE_SIZE_MAX)


def _paginate(rows, page, page_size):
    page, page_size = _page_args(page, page_size)
    total = len(rows)
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    return {
        "rows": rows[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _format_value(value, digits=1):
    try:
        return format(flt(value), f".{digits}f")
    except Exception:
        return "0"


def _has_location_filter(filters):
    return any(filters.get(key) for key in ("building", "building_block", "floor", "property"))


class DashboardContext:
    """Per-request, permission-aware source rows and calculated measures."""

    def __init__(self, filters):
        today = getdate()
        # No default date filters: when from_date/to_date are empty, use a very
        # wide range so no date filtering is applied (all time).
        default_from = date(1900, 1, 1)
        default_to = date(2100, 12, 31)
        self.from_date = _date(filters.get("from_date")) or default_from
        self.to_date = _date(filters.get("to_date")) or default_to
        if self.from_date > self.to_date:
            frappe.throw(_("From Date cannot be after To Date."))

        self.as_of = min(self.to_date, today)
        self.filters = {
            "from_date": _iso(self.from_date) if self.from_date.year > 1900 else "",
            "to_date": _iso(self.to_date) if self.to_date.year < 2100 else "",
            "as_of": _iso(self.as_of),
            "building": filters.get("building") or "",
            "building_block": filters.get("building_block") or "",
            "floor": filters.get("floor") or "",
            "property": filters.get("property") or "",
        }
        self.permissions = {}
        self.errors = {}
        self._properties = None
        self._contracts = None
        self._invoices = None
        self._exceptions = []

    def has_permission(self, doctype):
        if doctype not in self.permissions:
            self.permissions[doctype] = bool(frappe.has_permission(doctype, "read"))
        return self.permissions[doctype]

    def list_rows(self, doctype, filters, fields):
        if not self.has_permission(doctype):
            return []
        try:
            return frappe.get_list(
                doctype,
                filters=filters,
                fields=fields,
                limit_page_length=LIST_LIMIT,
                order_by="name asc",
            )
        except Exception as exc:
            error_id = frappe.log_error(
                title="PM Dashboard source query: " + doctype,
                message=frappe.get_traceback(),
            )
            self.errors[doctype] = str(error_id or "query-error")
            return []

    @property
    def properties(self):
        if self._properties is not None:
            return self._properties
        rows = self.list_rows(
            "Property",
            {"is_not_leasable": 0},
            [
                "name", "building", "building_block", "floor", "status", "rent",
                "area", "total_area_of_property", "total_area", "apt_no", "creation",
                "is_not_leasable",
            ],
        )
        self._properties = [
            row for row in rows
            if (not self.filters["building"] or row.building == self.filters["building"])
            and (not self.filters["building_block"] or row.building_block == self.filters["building_block"])
            and (not self.filters["floor"] or row.floor == self.filters["floor"])
            and (not self.filters["property"] or row.name == self.filters["property"])
        ]
        self.property_map = {row.name: row for row in self._properties}
        return self._properties

    @property
    def property_names(self):
        return [row.name for row in self.properties]

    @property
    def contracts(self):
        if self._contracts is not None:
            return self._contracts
        property_names = self.property_names
        if not property_names:
            self._contracts = []
            return self._contracts

        rows = self.list_rows(
            "Rent Contract",
            {"docstatus": 1, "property": ["in", property_names]},
            [
                "name", "property", "building", "tenant", "tenant_name",
                "contract_start_date", "contract_end_date", "monthly_payable_amount",
                "status", "multi_rent_contract_no", "extension_parent",
            ],
        )
        contracts = []
        for row in rows:
            row["monthly"] = flt(row.monthly_payable_amount)
            row["start"] = _date(row.contract_start_date)
            row["end"] = _date(row.contract_end_date)
            row["mprc"] = row.multi_rent_contract_no or ""
            row["doctype"] = "Rent Contract"
            row["document_name"] = row.name
            contracts.append(row)

        # MPRC child Rent Contract rows are never counted directly: each child
        # property row is already the canonical property-level contract. The MPRC
        # parent document itself is ignored everywhere, per your instruction.
        seen_contracts = set()
        unique = []
        for contract in contracts:
            key = (contract.property, contract.start, contract.end)
            if key in seen_contracts:
                self._exceptions.append({
                    "source": contract["name"],
                    "reason": "Duplicate property period excluded",
                    "amount": contract["monthly"],
                })
                continue
            seen_contracts.add(key)
            unique.append(contract)
        self._contracts = unique
        return self._contracts

    @property
    def invoices(self):
        if self._invoices is not None:
            return self._invoices
        rows = self.list_rows(
            "Sales Invoice",
            {
                "docstatus": 1,
                "is_property_invoice": 1,
                "invoice_type": "Rent",
                "is_return": 0,
                "posting_date": ["between", [self.filters["from_date"], self.filters["to_date"]]],
            },
            [
                "name", "posting_date", "due_date", "customer", "customer_name",
                "grand_total", "outstanding_amount", "status", "property", "building",
                "rent_contract", "contract_no", "multi_rent_contract_no",
                "period_start_date", "period_end_date", "cost_center",
            ],
        )
        contract_map = {c["name"]: c for c in self.contracts}
        mprc_contracts = defaultdict(list)
        for c in self.contracts:
            if c.get("mprc"):
                mprc_contracts[c["mprc"]].append(c)
        cost_center_buildings = {}
        if self.has_permission("Building"):
            for b in self.list_rows("Building", {}, ["name", "cost_center"]):
                if b.cost_center:
                    cost_center_buildings[b.cost_center] = b.name

        has_location = _has_location_filter(self.filters)
        output = []
        for inv in rows:
            invoice_property = inv.property
            if not invoice_property:
                rc = contract_map.get(inv.rent_contract or inv.contract_no)
                if rc:
                    invoice_property = rc.property
            # Skip activity on invisible/non-leasable units.
            if invoice_property and invoice_property not in self.property_map:
                continue
            building = (
                self.property_map[invoice_property].building
                if invoice_property in self.property_map
                else inv.building or cost_center_buildings.get(inv.cost_center) or ""
            )
            if has_location and self.filters["building"] and building != self.filters["building"]:
                continue
            row = frappe._dict(inv.copy())
            row.update({
                "property": invoice_property or "",
                "building": building,
                "due": flt(inv.grand_total),
                "collected": 0.0,
                "outstanding": flt(inv.grand_total),
            })
            output.append(row)

        # Collect allocations from Payment Entry References against these invoices.
        names = [row.name for row in output]
        if names:
            pes = self.list_rows(
                "Payment Entry",
                {"docstatus": 1, "payment_type": "Receive", "posting_date": ["<=", self.as_of]},
                ["name", "posting_date", "party", "received_amount", "total_allocated_amount"],
            )
            pe_map = {p.name: p for p in pes}
            if pe_map:
                refs = frappe.db.sql(
                    """
                    SELECT parent, reference_name, allocated_amount
                    FROM `tabPayment Entry Reference`
                    WHERE parent IN %(parents)s
                      AND reference_doctype = 'Sales Invoice'
                      AND reference_name IN %(invoices)s
                    """,
                    {"parents": tuple(pe_map), "invoices": tuple(names)},
                    as_dict=True,
                )
                allocations = defaultdict(list)
                for ref in refs:
                    pe = pe_map.get(ref.parent)
                    if not pe:
                        continue
                    allocations[ref.reference_name].append({
                        "payment": pe.name,
                        "payment_date": _date(pe.posting_date),
                        "party": pe.party,
                        "allocated": flt(ref.allocated_amount),
                        "cash_received": flt(pe.received_amount),
                    })
                for row in output:
                    refs_list = allocations.get(row.name, [])
                    total_allocated = sum(r["allocated"] for r in refs_list)
                    row.collected = min(max(row.due, 0), max(total_allocated, 0))
                    row.outstanding = row.due - row.collected
                    row.allocation_rows = refs_list
            else:
                for row in output:
                    row.allocation_rows = []
        else:
            for row in output:
                row.allocation_rows = []

        self._invoices = output
        return self._invoices

    def active_contracts_on(self, target_date):
        """Contracts effective on target_date, one per property."""
        active = []
        for c in self.contracts:
            if c.start <= target_date <= c.end:
                active.append(c)
        return active

    def occupancy(self):
        active = self.active_contracts_on(self.as_of)
        return {c.property for c in active}, active

    def building_labels(self):
        if not self.has_permission("Building"):
            return {}
        rows = self.list_rows("Building", {}, ["name", "building_name"])
        return {row.name: row.building_name or row.name for row in rows}

    def expiries(self):
        today = getdate()
        end = add_days(today, 30)
        rows = []
        for c in self.contracts:
            if today <= c.end <= end:
                row = {
                    "name": c["name"],
                    "document_name": c["name"],
                    "doctype": "Rent Contract",
                    "contract": c["name"],
                    "tenant": c.get("tenant_name") or c.get("tenant") or "",
                    "property": c.property,
                    "property_label": self.property_map.get(c.property, {}).apt_no or c.property,
                    "building": c.building,
                    "end_date": c.end,
                    "days_to_expiry": (c.end - today).days,
                    "monthly": c.monthly,
                }
                rows.append(row)
        return sorted(rows, key=lambda r: (r["end_date"], r["contract"]))

    def pre_booked(self):
        today = getdate()
        end = add_months(today, 12)
        rows = []
        for c in self.contracts:
            if today < c.start <= end:
                rows.append({
                    "name": c["name"],
                    "document_name": c["name"],
                    "doctype": "Rent Contract",
                    "contract": c["name"],
                    "tenant": c.get("tenant_name") or c.get("tenant") or "",
                    "property": c.property,
                    "property_label": self.property_map.get(c.property, {}).apt_no or c.property,
                    "building": c.building,
                    "start": c.start,
                    "end": c.end,
                    "monthly": c.monthly,
                })
        return sorted(rows, key=lambda r: (r["start"], r["contract"]))

    def vacancy_rows(self):
        occupied, _ = self.occupancy()
        rows = []
        for prop in self.properties:
            if prop.name in occupied:
                continue
            prior_ends = [
                c.end for c in self.contracts
                if c.property == prop.name and c.end < self.as_of
            ]
            future = [
                c for c in self.contracts
                if c.property == prop.name and c.start > self.as_of
            ]
            start = add_days(max(prior_ends), 1) if prior_ends else _date(prop.creation)
            if not start:
                start = self.as_of
            start = min(start, self.as_of)
            days = max(0, (self.as_of - start).days)
            rent = flt(prop.rent)
            loss_start = max(start, self.from_date)
            loss_end = min(self.as_of, self.to_date)
            loss = prorated_monthly(rent, start, self.as_of, loss_start, loss_end) if loss_start <= loss_end else 0.0
            area = flt(prop.total_area_of_property or prop.total_area or prop.area)
            rows.append({
                "property": prop.name,
                "property_label": prop.apt_no or prop.name,
                "building": prop.building or "",
                "building_block": prop.building_block or "",
                "floor": prop.floor or "",
                "area": area,
                "vacancy_start": start,
                "days_vacant": days,
                "potential_rent": rent,
                "revenue_loss": round(loss, 2),
                "missing_potential_rent": rent <= 0,
                "last_contract": max(prior_ends) if prior_ends else None,
                "next_contract": min((c.start for c in future), default=None),
                "pre_booked": bool(future),
            })
        return rows

    def _visible_names(self, doctype, values):
        values = [v for v in values if v]
        if not values or not self.has_permission(doctype):
            return set()
        rows = self.list_rows(doctype, {"name": ["in", values]}, ["name"])
        return {row.name for row in rows}


def _card(key, label, value, source, subtitle="", status="normal", unit="number"):
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "subtitle": subtitle,
        "status": status,
        "source_doctype": source,
    }


def _rows_for_kpi(ctx, kpi):
    """Return rows, columns, totals, reconciliation for a drill-down dialog."""
    columns = []
    totals = {}
    reconciliation = []

    if kpi == "overview.total_units":
        occupied, _ = ctx.occupancy()
        props = ctx.properties
        rows = []
        for p in props:
            rows.append({
                "property": p.name,
                "property_label": p.apt_no or p.name,
                "building": p.building or "",
                "building_block": p.building_block or "",
                "floor": p.floor or "",
                "area": flt(p.total_area_of_property or p.total_area or p.area),
                "status": "Occupied" if p.name in occupied else "Vacant",
            })
        columns = [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("status", "Status", "text", ""),
        ]
        totals = {"total_units": len(props), "occupied": sum(1 for p in props if p.name in occupied)}
        reconciliation = [
            {"label": "Occupied units", "amount": totals["occupied"], "sign": ""},
            {"label": "Vacant units", "amount": len(props) - totals["occupied"], "sign": "+"},
            {"label": "Total leasable units", "amount": totals["total_units"], "sign": "="},
        ]
        return rows, columns, totals, reconciliation

    # overview.total_area / overview.occupied_area / overview.occupancy_rate /
    # overview.area_occupancy_rate open NOTHING on click.
    if kpi in ("overview.total_area", "overview.occupied_area", "overview.occupancy_rate",
               "overview.area_occupancy_rate"):
        return [], [], {}, []

    if kpi == "overview.occupied_units":
        occupied, _ = ctx.occupancy()
        props = ctx.properties
        rows = []
        for p in props:
            if p.name not in occupied:
                continue
            rows.append({
                "property": p.name,
                "property_label": p.apt_no or p.name,
                "building": p.building or "",
                "building_block": p.building_block or "",
                "floor": p.floor or "",
                "area": flt(p.total_area_of_property or p.total_area or p.area),
                "status": "Occupied",
            })
        columns = [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("status", "Status", "text", ""),
        ]
        return rows, columns, {"occupied_units": len(rows)}, []

    if kpi == "overview.vacant_units":
        return ctx.vacancy_rows(), [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("days_vacant", "Days Vacant", "number", ""),
            ("potential_rent", "Potential Rent / Month", "money", ""),
            ("revenue_loss", "Revenue Loss", "money", ""),
        ], {"vacant_units": len(ctx.vacancy_rows())}, []

    if kpi == "overview.expiring_30d":
        rows = ctx.expiries()
        for r in rows:
            r["days_left"] = r["days_to_expiry"]
        return rows, [
            ("contract", "Contract", "link", "Rent Contract"),
            ("tenant", "Tenant", "text", ""),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("end_date", "End Date", "date", ""),
            ("days_left", "Days Left", "number", ""),
            ("monthly", "Monthly Rent", "money", ""),
        ], {"expiring_30d": len(rows)}, []

    if kpi.startswith("revenue.rental_income_gl"):
        # One row per contract (RC or its MPRC parent), never per-month, never
        # child-expanded. Columns: Contract (link), Tenant, Start, End, Monthly Rent.
        def contract_label(c):
            mprc = c.get("multi_rent_contract_no") or c.get("mprc")
            if mprc:
                return {"doctype": "Multi Property Rent Contract", "name": mprc}
            return {"doctype": "Rent Contract", "name": c["name"]}

        seen = {}
        for c in ctx.contracts:
            label = contract_label(c)
            key = label["name"]
            if key not in seen:
                seen[key] = {
                    "contract": label["name"],
                    "contract_doctype": label["doctype"],
                    "source_doctype": label["doctype"],
                    "source_name": label["name"],
                    "tenant": c.get("tenant_name") or c.get("tenant") or "",
                    "start": c.start,
                    "end": c.end,
                    "monthly": flt(c.monthly),
                }
        rows = list(seen.values())
        return rows, [
            ("contract", "Contract", "link_dynamic", ""),
            ("tenant", "Tenant", "text", ""),
            ("start", "Start", "date", ""),
            ("end", "End", "date", ""),
            ("monthly", "Monthly Rent", "money", ""),
        ], {"rental_income": round(sum(r["monthly"] for r in rows), 2), "contract_count": len(rows)}, []

    if kpi.startswith("revenue.invoiced_rent"):
        rows = ctx.invoices
        return rows, [
            ("name", "Rent Invoice", "link", "Sales Invoice"),
            ("posting_date", "Posting Date", "date", ""),
            ("due_date", "Due Date", "date", ""),
            ("customer_name", "Tenant", "text", ""),
            ("property", "Property", "text", ""),
            ("building", "Building", "text", ""),
            ("due", "Invoiced Amount", "money", ""),
            ("outstanding", "Still Outstanding", "money", ""),
            ("status", "Status", "text", ""),
        ], {
            "invoiced_rent": round(sum(r.due for r in rows), 2),
            "outstanding": round(sum(r.outstanding for r in rows), 2),
        }, []

    if kpi.startswith("revenue.collected"):
        rows = []
        for inv in ctx.invoices:
            for alloc in inv.allocation_rows:
                if alloc["allocated"] > 0:
                    rows.append({
                        "payment": alloc["payment"],
                        "payment_date": alloc["payment_date"],
                        "party": alloc["party"],
                        "invoice": inv.name,
                        "invoice_date": inv.posting_date,
                        "property": inv.property,
                        "building": inv.building,
                        "allocated": alloc["allocated"],
                        "cash_received": alloc["cash_received"],
                    })
        return rows, [
            ("payment", "Payment Entry", "link", "Payment Entry"),
            ("payment_date", "Payment Date", "date", ""),
            ("party", "Customer", "text", ""),
            ("invoice", "Rent Invoice", "link", "Sales Invoice"),
            ("invoice_date", "Invoice Date", "date", ""),
            ("property", "Property", "text", ""),
            ("building", "Building", "text", ""),
            ("allocated", "Allocated", "money", ""),
            ("cash_received", "Cash Received", "money", ""),
        ], {
            "collected": round(sum(r["allocated"] for r in rows), 2),
            "payment_count": len({r["payment"] for r in rows}),
        }, []

    if kpi.startswith("revenue.outstanding"):
        rows = [r for r in ctx.invoices if flt(r.outstanding) > 0]
        return rows, [
            ("name", "Rent Invoice", "link", "Sales Invoice"),
            ("posting_date", "Posting Date", "date", ""),
            ("due_date", "Due Date", "date", ""),
            ("customer_name", "Tenant", "text", ""),
            ("property", "Property", "text", ""),
            ("building", "Building", "text", ""),
            ("due", "Invoiced Amount", "money", ""),
            ("collected", "Collected", "money", ""),
            ("outstanding", "Still Outstanding", "money", ""),
            ("status", "Status", "text", ""),
        ], {
            "invoiced_rent": round(sum(r.due for r in ctx.invoices), 2),
            "collected": round(sum(r.collected for r in ctx.invoices), 2),
            "outstanding": round(sum(r.outstanding for r in rows), 2),
        }, []

    if kpi.startswith("revenue.collection_rate"):
        return [], [], {}, []

    if kpi.startswith("vacancy.vacant_units"):
        rows = ctx.vacancy_rows()
        return rows, [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("vacancy_start", "Vacancy Start", "date", ""),
            ("days_vacant", "Days Vacant", "number", ""),
            ("potential_rent", "Potential Rent / Month", "money", ""),
            ("revenue_loss", "Revenue Loss", "money", ""),
        ], {"vacant_units": len(rows)}, []

    if kpi.startswith("vacancy.days_60_plus"):
        # Properties that have been vacant for 60 days or more, based on
        # vacancy duration (as_of minus vacancy start), filtered by all filters.
        rows = [r for r in ctx.vacancy_rows() if r["days_vacant"] >= 60]
        return rows, [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("vacancy_start", "Vacancy Start", "date", ""),
            ("days_vacant", "Days Vacant", "number", ""),
            ("potential_rent", "Potential Rent / Month", "money", ""),
            ("revenue_loss", "Revenue Loss", "money", ""),
        ], {"vacant_60_plus": len(rows)}, []

    if kpi.startswith("vacancy.revenue_loss"):
        return [], [], {}, []

    if kpi.startswith("vacancy.vacancy_rate"):
        return [], [], {}, []

    if kpi.startswith("contract_value.active_contracts"):
        # One row per contract (MPRC parent if child RC belongs to one), no
        # child expansion. Contracts effective on ctx.to_date.
        seen = {}
        for c in ctx.active_contracts_on(ctx.to_date):
            mprc = c.get("multi_rent_contract_no") or c.get("mprc")
            name = mprc or c["name"]
            if name not in seen:
                seen[name] = {
                    "contract": name,
                    "contract_doctype": "Multi Property Rent Contract" if mprc else "Rent Contract",
                    "source_doctype": "Multi Property Rent Contract" if mprc else "Rent Contract",
                    "source_name": mprc or c["name"],
                    "tenant": c.get("tenant_name") or c.get("tenant") or "",
                    "start": c.start,
                    "end": c.end,
                    "monthly": c.monthly,
                }
        rows = list(seen.values())
        return rows, [
            ("contract", "Contract", "link_dynamic", ""),
            ("tenant", "Tenant", "text", ""),
            ("start", "Start", "date", ""),
            ("end", "End", "date", ""),
            ("monthly", "Monthly Rent", "money", ""),
        ], {"active_contracts": len(rows)}, []

    if kpi.startswith("contract_value.awaiting_renewal"):
        return ctx.expiries(), [
            ("name", "Contract", "link", "Rent Contract"),
            ("tenant", "Tenant", "text", ""),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("end_date", "End Date", "date", ""),
            ("days_to_expiry", "Days Left", "number", ""),
            ("monthly", "Monthly Rent", "money", ""),
        ], {"awaiting_renewal": len(ctx.expiries())}, []

    if kpi.startswith("contract_value.pre_booked"):
        rows = ctx.pre_booked()
        return rows, [
            ("name", "Contract", "link", "Rent Contract"),
            ("tenant", "Tenant", "text", ""),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("start", "Start", "date", ""),
            ("end", "End", "date", ""),
            ("monthly", "Monthly Rent", "money", ""),
        ], {"pre_booked": len(rows)}, []

    if kpi in ("overview.total_area", "overview.occupied_area", "overview.occupancy_rate", "overview.occupied_units", "overview.area_occupancy_rate"):
        return _rows_for_overview_area(kpi, ctx)

    frappe.throw(f"Unknown KPI: {kpi}")


def _rows_for_overview_area(kpi, ctx):
    occupied, _ = ctx.occupancy()
    rows = []
    for p in ctx.properties:
        is_occupied = p.name in occupied
        if kpi == "overview.total_area":
            pass
        elif kpi == "overview.occupied_area" and not is_occupied:
            continue
        elif kpi == "overview.occupancy_rate" or kpi == "overview.occupied_units" or kpi == "overview.area_occupancy_rate":
            continue
        rows.append({
            "property": p.name,
            "property_label": p.apt_no or p.name,
            "building": p.building or "",
            "building_block": p.building_block or "",
            "floor": p.floor or "",
            "area": flt(p.total_area_of_property or p.total_area or p.area),
            "status": "Occupied" if is_occupied else "Vacant",
        })
    if kpi == "overview.total_area" or kpi == "overview.area_occupancy_rate":
        columns = [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("building_block", "Block", "text", ""),
            ("floor", "Floor", "text", ""),
            ("area", "Area", "number", ""),
            ("status", "Status", "text", ""),
        ]
        total = round(sum(flt(r["area"]) for r in rows), 2)
        occupied = round(sum(flt(r["area"]) for r in rows if r["status"] == "Occupied"), 2)
        return rows, columns, {"total_area": total, "occupied_area": occupied, "area_occupancy_rate": round(100 * occupied / total, 2) if total else 0}, []
    if kpi == "overview.occupied_area":
        columns = [
            ("property", "Property", "link", "Property"),
            ("property_label", "Unit", "text", ""),
            ("building", "Building", "text", ""),
            ("area", "Area", "number", ""),
        ]
        return rows, columns, {"occupied_area": round(sum(flt(r["area"]) for r in rows), 2)}, []
    return [], [], {}, []


def details_data(ctx, kpi, page=1, page_size=PAGE_SIZE_DEFAULT):
    rows, columns, totals, reconciliation = _rows_for_kpi(ctx, kpi)
    # columns arrive as tuples; normalise to dicts here.
    columns = [
        {"key": key, "label": label, "type": kind, "doctype": doctype}
        for key, label, kind, doctype in columns
    ]
    # Make dates JSON-safe and attach source links only for permitted targets.
    visible_targets = defaultdict(set)
    for row in rows:
        links = {}
        for column in columns:
            key = column["key"]
            if column["type"] == "link":
                doctype = column.get("doctype")
                name = row.get(key)
            elif column["type"] == "link_dynamic":
                doctype = row.get("source_doctype") or row.get("doctype")
                name = row.get("source_name") or row.get(key)
            else:
                continue
            if doctype and name:
                links[key] = {"doctype": doctype, "name": name}
                visible_targets[doctype].add(name)
        row["_links"] = links

    allowed_by_doctype = {}
    for doctype, names in visible_targets.items():
        allowed_by_doctype[doctype] = ctx._visible_names(doctype, names)
    for row in rows:
        row_links = {}
        for key, target in row.get("_links", {}).items():
            if target["name"] in allowed_by_doctype.get(target["doctype"], set()):
                row_links[key] = target
        row["_links"] = row_links

    clean_rows = []
    for row in rows:
        clean = {}
        for key, value in row.items():
            if key == "_links":
                clean[key] = value
                continue
            if isinstance(value, date):
                clean[key] = value.isoformat()
            else:
                clean[key] = value
        clean_rows.append(clean)

    result = _paginate(clean_rows, page, page_size)
    page_rows = result["rows"]

    period = {key: value for key, value in ctx.filters.items() if value}
    return {
        "kpi": kpi,
        "label": kpi.split(".")[-1].replace("_", " ").title(),
        "period": period,
        "filters": {key: ctx.filters.get(key) or "" for key in ("building", "building_block", "floor", "property")},
        "columns": columns,
        "rows": page_rows,
        "totals": totals,
        "reconciliation": reconciliation,
        "page": result["page"],
        "page_size": result["page_size"],
        "total": result["total"],
        "total_pages": result["total_pages"],
        "permission": {"allowed": True},
        "exceptions": ctx._exceptions,
        "errors": ctx.errors,
    }


def overview_data(ctx):
    props = ctx.properties
    occupied, _ = ctx.occupancy()
    total_area = sum(flt(p.total_area_of_property or p.total_area or p.area) for p in props)
    occupied_area = sum(
        flt(p.total_area_of_property or p.total_area or p.area)
        for p in props if p.name in occupied
    )
    area_rate = 100 * occupied_area / total_area if total_area else 0
    # Per-building occupancy for charts
    building_map = {}
    for p in props:
        b = p.building or "Unknown"
        if b not in building_map:
            building_map[b] = {"building": b, "occupied_units": 0, "vacant_units": 0}
        if p.name in occupied:
            building_map[b]["occupied_units"] += 1
        else:
            building_map[b]["vacant_units"] += 1
    buildings = []
    for b, v in building_map.items():
        total = v["occupied_units"] + v["vacant_units"]
        buildings.append({
            "building": b,
            "occupancy_rate": round(100 * v["occupied_units"] / total, 2) if total else 0,
            "occupied_units": v["occupied_units"],
            "vacant_units": v["vacant_units"],
        })
    summary = {
        "total_buildings": len({p.building for p in props if p.building}),
        "total_blocks": len({(p.building, p.building_block) for p in props}),
        "total_floors": len({(p.building, p.floor) for p in props}),
        "total_units": len(props),
        "occupied_units": sum(1 for p in props if p.name in occupied),
        "vacant_units": sum(1 for p in props if p.name not in occupied),
        "occupancy_rate": 100 * sum(1 for p in props if p.name in occupied) / len(props) if props else 0,
        "area_occupancy_rate": area_rate,
        "total_area": total_area,
        "occupied_area": occupied_area,
        "buildings": buildings,
    }
    return {
        "cards": [
            _card("overview.total_units", "Total Units", summary["total_units"], "Property", unit="count"),
            _card("overview.total_area", "Total Area", summary["total_area"], "Property", unit="area"),
            _card("overview.occupied_area", "Occupied Area", summary["occupied_area"], "Property", unit="area"),
            _card("overview.area_occupancy_rate", "Occupancy Rate", summary["area_occupancy_rate"], "Property", unit="percent"),
            _card("overview.occupied_units", "Occupied Units", summary["occupied_units"], "Rent Contract", unit="count"),
            _card("overview.vacant_units", "Vacant Units", summary["vacant_units"], "Property", unit="count"),
        ],
        "summary": summary,
        "period": ctx.filters,
        "errors": ctx.errors,
        "exceptions": ctx._exceptions,
    }


def revenue_data(ctx):
    due = sum(flt(r.due) for r in ctx.invoices)
    collected = sum(flt(r.collected) for r in ctx.invoices)
    outstanding = sum(flt(r.outstanding) for r in ctx.invoices)
    rate = 100 * collected / due if due else 0
    rental_income = 0.0
    for c in ctx.contracts:
        for month in _months_between(ctx.from_date, ctx.to_date):
            seg_start = max(c.start, ctx.from_date, month)
            seg_end = min(c.end, ctx.to_date, _month_end(month))
            if seg_start > seg_end:
                continue
            days_in_month = _month_end(month).day
            days = (seg_end - seg_start).days + 1
            rental_income += flt(c.monthly) * days / days_in_month
    return {
        "cards": [
            _card("revenue.rental_income_gl", "Rental Income", round(rental_income, 2), "Rent Contract", "Active RC monthly rent in period", "normal", "money"),
            _card("revenue.invoiced_rent", "Invoiced Rent", round(due, 2), "Sales Invoice", "Submitted rent invoices in period", "normal", "money"),
            _card("revenue.collected", "Collected", round(collected, 2), "Payment Entry", "Allocations against period invoices", "normal", "money"),
            _card("revenue.outstanding", "Outstanding Rent", round(outstanding, 2), "Sales Invoice", "Invoiced minus collected", "normal", "money"),
            _card("revenue.collection_rate", "Collection Rate", round(rate, 2), "Sales Invoice", "Collected ÷ Rent Due", "normal", "percent"),
        ],
        "summary": {
            "rental_income": round(rental_income, 2),
            "invoiced_rent": round(due, 2),
            "collected": round(collected, 2),
            "outstanding": round(outstanding, 2),
            "collection_rate": round(rate, 2),
        },
        "charts": {"monthly": monthly_trend(ctx)},
        "period": ctx.filters,
        "errors": ctx.errors,
        "exceptions": ctx._exceptions,
    }


def monthly_trend(ctx):
    """Month-by-month rental income, invoiced rent, collected, outstanding."""
    rentals = defaultdict(float)
    invoiced = defaultdict(float)
    collected_m = defaultdict(float)
    outstanding_m = defaultdict(float)
    for c in ctx.contracts:
        for month in _months_between(ctx.from_date, ctx.to_date):
            seg_start = max(c.start, ctx.from_date, month)
            seg_end = min(c.end, ctx.to_date, _month_end(month))
            if seg_start > seg_end:
                continue
            days_in_month = _month_end(month).day
            days = (seg_end - seg_start).days + 1
            rentals[month] += flt(c.monthly) * days / days_in_month
    for inv in ctx.invoices:
        month = getdate(inv.posting_date).replace(day=1)
        invoiced[month] += flt(inv.due)
        collected_m[month] += flt(inv.collected)
        outstanding_m[month] += flt(inv.outstanding)
    months = _months_between(ctx.from_date, ctx.to_date)
    # When no date filter is set, show only the last 24 months from today so
    # the chart stays performant and readable (not 1900-2100).
    if not filters_have_dates(ctx.filters):
        from datetime import date as _date
        from frappe.utils import add_months as _add_months
        today = getdate()
        months = []
        m = today.replace(day=1)
        for _ in range(24):
            months.append(m)
            m = _add_months(m, -1)
        months = sorted(months)
    return [
        {
            "month": _iso(month),
            "rental_income": round(rentals[month], 2),
            "invoiced_rent": round(invoiced[month], 2),
            "collected": round(collected_m[month], 2),
            "outstanding": round(outstanding_m[month], 2),
        }
        for month in months
    ]


def filters_have_dates(filters):
    return bool(filters.get("from_date") or filters.get("to_date"))


def vacancy_data(ctx):
    rows = ctx.vacancy_rows()
    total = len(ctx.properties)
    vacant = len(rows)
    vacant_60 = sum(1 for r in rows if r["days_vacant"] > 60)
    loss = round(sum(flt(r["revenue_loss"]) for r in rows), 2)
    missing = sum(1 for r in rows if r["missing_potential_rent"])
    return {
        "cards": [
            _card("vacancy.vacant_units", "Vacant Units", vacant, "Property", unit="count"),
            _card("vacancy.vacancy_rate", "Vacancy Rate", round(100 * vacant / total, 2) if total else 0, "Property", unit="percent"),
            _card("vacancy.days_60_plus", "Vacant 60+ Days", vacant_60, "Property", unit="count"),
            _card("vacancy.revenue_loss", "Revenue Loss", loss, "Property", "Based on Property Potential Rent only", "data-gap" if missing else "normal", "money"),
        ],
        "summary": {
            "total_units": total,
            "vacant_units": vacant,
            "vacancy_rate": round(100 * vacant / total, 2) if total else 0,
            "vacant_60_plus": vacant_60,
            "revenue_loss": loss,
            "missing_potential_rent": missing,
        },
        "charts": {
            "by_building": vacancy_by_building(ctx),
            "duration": vacancy_duration(ctx),
        },
        "tables": {"vacant_properties": rows},
        "period": ctx.filters,
        "errors": ctx.errors,
        "exceptions": ctx._exceptions,
    }


def contract_value_data(ctx):
    active = ctx.active_contracts_on(ctx.to_date)
    prebooked = ctx.pre_booked()
    return {
        "cards": [
            _card("contract_value.active_contracts", "Active Contracts", len(active), "Rent Contract", unit="count"),
            _card("contract_value.awaiting_renewal", "Awaiting Renewal", len(ctx.expiries()), "Rent Contract", "Expiring in next 30 days", "normal", "count"),
            _card("contract_value.pre_booked", "Pre-Booked Contracts", len(prebooked), "Rent Contract", "Starts in next 12 months", "normal", "count"),
        ],
        "summary": {
            "active_contracts": len(active),
            "awaiting_renewal": len(ctx.expiries()),
            "pre_booked": len(prebooked),
        },
        "tables": {
            "active_contracts": active,
            "pre_booked": prebooked,
        },
        "period": ctx.filters,
        "errors": ctx.errors,
        "exceptions": ctx._exceptions,
    }


def vacancy_by_building(ctx):
    grouped = defaultdict(int)
    for p in ctx.properties:
        occupied, _ = ctx.occupancy()
        if p.name not in occupied:
            grouped[p.building or "Unknown"] += 1
    return [
        {"building": b, "vacant_units": n}
        for b, n in sorted(grouped.items())
    ]


def vacancy_duration(ctx):
    buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in ctx.vacancy_rows():
        d = r["days_vacant"]
        if d <= 30:
            buckets["0-30"] += 1
        elif d <= 60:
            buckets["31-60"] += 1
        elif d <= 90:
            buckets["61-90"] += 1
        else:
            buckets["90+"] += 1
    return [{"bucket": k, "units": v} for k, v in buckets.items()]


def dashboard_data(tab, filters):
    ctx = DashboardContext(filters)
    if not ctx.has_permission("Property"):
        frappe.throw(_("You do not have permission to read Property records."), frappe.PermissionError)
    providers = {
        "overview": overview_data,
        "revenue": revenue_data,
        "vacancy": vacancy_data,
        "contract_value": contract_value_data,
    }
    if tab not in providers:
        frappe.throw(_("Unknown dashboard tab: {0}").format(tab))
    result = providers[tab](ctx)
    for card in result.get("cards", []):
        doctype = card["source_doctype"]
        allowed = ctx.has_permission(doctype)
        card["permission"] = {"allowed": allowed, "doctype": doctype}
        if not allowed:
            card["value"] = None
            card["status"] = "locked"
    result["filters"] = ctx.filters
    result.setdefault("exceptions", ctx._exceptions)
    return result


# Whitelisted API endpoints for the PM Dashboard page.

def _filters(from_date="", to_date="", building="", building_block="", floor="", property=""):
    return {
        "from_date": from_date or "",
        "to_date": to_date or "",
        "building": building or "",
        "building_block": building_block or "",
        "floor": floor or "",
        "property": property or "",
    }


@frappe.whitelist()
def get_dashboard(tab="overview", from_date="", to_date="", building="", building_block="", floor="", property=""):
    """Return one lazily-loaded dashboard index."""
    filters = _filters(from_date, to_date, building, building_block, floor, property)
    try:
        return dashboard_data(tab, filters)
    except frappe.PermissionError:
        raise
    except Exception:
        error_id = frappe.log_error(
            title="PM Dashboard load error",
            message=frappe.get_traceback(),
        )
        frappe.throw(
            _("Unable to load the dashboard. Reference: {0}").format(error_id or "error"),
            title=_("Dashboard unavailable"),
        )


@frappe.whitelist()
def get_kpi_details(kpi="", from_date="", to_date="", building="", building_block="", floor="", property="", page=1, page_size=25):
    """Return the reconciling rows for a KPI, with server response pagination."""
    filters = _filters(from_date, to_date, building, building_block, floor, property)
    ctx = DashboardContext(filters)
    source_map = {
        "revenue.rental_income_gl": "Rent Contract",
        "revenue.invoiced_rent": "Sales Invoice",
        "revenue.collected": "Payment Entry",
        "revenue.outstanding": "Sales Invoice",
        "revenue.collection_rate": "Sales Invoice",
    }
    source = source_map.get(kpi)
    if kpi.startswith("overview."):
        source = "Rent Contract" if kpi in ("overview.total_units", "overview.occupied_units", "overview.expiring_30d") else "Property"
    elif kpi.startswith("vacancy."):
        source = "Property"
    elif kpi.startswith("contract_value."):
        source = "Rent Contract"
    if not source:
        frappe.throw(_("Unknown KPI: {0}").format(kpi))
    # MPRC parents are permitted too: a Rent Contract child under an MPRC is
    # allowed if the user can read the MPRC parent.
    allow_mprc = kpi.startswith(("revenue.rental_income_gl", "contract_value.active_contracts"))
    if not allow_mprc and not ctx.has_permission(source):
        return {
            "kpi": kpi,
            "label": kpi.split(".")[-1].replace("_", " ").title(),
            "permission": {"allowed": False, "doctype": source},
            "columns": [],
            "rows": [],
            "totals": {},
            "reconciliation": [],
            "page": 1,
            "page_size": 25,
            "total": 0,
            "total_pages": 1,
        }
    if allow_mprc and not (ctx.has_permission("Rent Contract") or ctx.has_permission("Multi Property Rent Contract")):
        return {
            "kpi": kpi,
            "label": kpi.split(".")[-1].replace("_", " ").title(),
            "permission": {"allowed": False, "doctype": "Rent Contract"},
            "columns": [],
            "rows": [],
            "totals": {},
            "reconciliation": [],
            "page": 1,
            "page_size": 25,
            "total": 0,
            "total_pages": 1,
        }
    return details_data(ctx, kpi, page, page_size)


@frappe.whitelist()
def get_filter_options(building="", building_block="", floor="", property=""):
    """Return cascading options from the user's permitted leasable properties."""
    base = DashboardContext(_filters())
    if not base.has_permission("Property"):
        frappe.throw(_("You do not have permission to read Property records."), frappe.PermissionError)
    properties = base.properties

    def matches(row, skip=""):
        checks = {
            "building": building,
            "building_block": building_block,
            "floor": floor,
            "property": property,
        }
        for key, selected in checks.items():
            if key == skip or not selected:
                continue
            field = "name" if key == "property" else key
            if getattr(row, field, "") != selected:
                return False
        return True

    buildings_for_options = [row for row in properties if matches(row, "building")]
    blocks_for_options = [row for row in properties if matches(row, "building_block")]
    floors_for_options = [row for row in properties if matches(row, "floor")]
    properties_for_options = [row for row in properties if matches(row, "property")]

    building_names = sorted({row.building for row in buildings_for_options if row.building})
    building_labels = {}
    if base.has_permission("Building") and building_names:
        docs = frappe.get_list(
            "Building",
            filters={"name": ["in", building_names]},
            fields=["name", "building_name"],
            limit_page_length=1000,
        )
        building_labels = {row.name: row.building_name or row.name for row in docs}

    return {
        "buildings": [{"value": name, "label": building_labels.get(name, name)} for name in building_names],
        "building_blocks": [{"value": v, "label": v} for v in sorted({row.building_block for row in blocks_for_options if row.building_block})],
        "floors": [{"value": v, "label": v} for v in sorted({row.floor for row in floors_for_options if row.floor})],
        "properties": [
            {"value": row.name, "label": row.apt_no or row.name}
            for row in sorted(properties_for_options, key=lambda item: (item.apt_no or item.name).lower())
        ],
    }

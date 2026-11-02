frappe.pages['pm-dashboard'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'PM Dashboard',
        single_column: true
    });
    new PMDashboard(page, wrapper);
};

const PM_API = 'pm_dashboard.pm_dashboard.page.pm_dashboard.pm_dashboard.';

class PMDashboard {
    constructor(page, wrapper) {
        this.page = page;
        this.tab = 'overview';
        this.chart = null;
        this.tabs = {
            overview: 'Overview',
            revenue: 'Revenue & Collections',
            vacancy: 'Vacancy & Performance'
        };
        this.make_layout(wrapper);
        this.make_filters();
        this.page.set_primary_action(__('Refresh'), () => this.load(), 'refresh');
        this.load();
    }

    // ------------------------------------------------------------ filters

    make_filters() {
        this.opts = {};
        this.load_debounced = frappe.utils.debounce(() => this.load(), 300);
        const cascade = () => this.load_options(() => this.load_debounced());

        const $wrap = $('<div class="pm-filters" style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin-bottom:12px"></div>')
            .insertBefore(this.$tabs);

        const make = (df) => {
            const $c = $('<div style="min-width:170px"></div>').appendTo($wrap);
            const ctrl = frappe.ui.form.make_control({ parent: $c, df: df, render_input: true });
            ctrl.refresh();
            return ctrl;
        };

        // Link search only offers values that fit the other selected filters
        const narrow = (key) => () => {
            const list = this.opts && this.opts[key];
            if (!list) return {};
            return { filters: { name: ['in', list.map(i => i.value)] } };
        };

        this.from_ctrl = make({
            fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date',
            change: () => this.load_debounced()
        });
        this.to_ctrl = make({
            fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date',
            change: () => this.load_debounced()
        });

        this.building_ctrl = make({
            fieldname: 'building', label: __('Building'), fieldtype: 'Link', options: 'Building',
            get_query: narrow('buildings'), change: cascade
        });
        this.block_ctrl = make({
            fieldname: 'building_block', label: __('Building Block'), fieldtype: 'Link',
            options: 'Building Block', get_query: narrow('building_blocks'), change: cascade
        });
        this.floor_ctrl = make({
            fieldname: 'floor', label: __('Floor'), fieldtype: 'Link', options: 'Floor',
            get_query: narrow('floors'), change: cascade
        });
        this.property_ctrl = make({
            fieldname: 'property', label: __('Property'), fieldtype: 'Link', options: 'Property',
            get_query: narrow('properties'), change: () => this.load_debounced()
        });

        $('<button class="btn btn-default btn-sm" style="margin-bottom:var(--margin-md, 12px)">Clear</button>')
            .appendTo($wrap)
            .on('click', () => {
                ['from_ctrl', 'to_ctrl', 'building_ctrl', 'block_ctrl', 'floor_ctrl', 'property_ctrl']
                    .forEach(k => this[k].set_value(''));
                this.load_options(() => this.load_debounced());
            });

        this.load_options();
    }

    load_options(done) {
        const f = this.filters();
        frappe.call({
            method: PM_API + 'get_filter_options',
            args: {
                building: f.building,
                building_block: f.building_block,
                floor: f.floor,
                property: f.property
            },
            callback: (r) => {
                const o = r.message || {};
                this.opts = o;
                // clear selections that no longer fit the other filters
                const valid = (list, v) => !v || (list || []).some(i => String(i.value) === String(v));
                if (!valid(o.buildings, f.building)) this.building_ctrl.set_value('');
                if (!valid(o.building_blocks, f.building_block)) this.block_ctrl.set_value('');
                if (!valid(o.floors, f.floor)) this.floor_ctrl.set_value('');
                if (!valid(o.properties, f.property)) this.property_ctrl.set_value('');
                if (done) done();
            }
        });
    }

    filters() {
        const from_date = this.from_ctrl.get_value() || '';
        const to_date = this.to_ctrl.get_value() || '';
        if (from_date && to_date && from_date > to_date) {
            frappe.show_alert({ message: __('From Date cannot be after To Date'), indicator: 'orange' });
        }
        return {
            from_date: from_date,
            to_date: to_date,
            building: this.building_ctrl ? (this.building_ctrl.get_value() || '') : '',
            building_block: this.block_ctrl ? (this.block_ctrl.get_value() || '') : '',
            floor: this.floor_ctrl ? (this.floor_ctrl.get_value() || '') : '',
            property: this.property_ctrl ? (this.property_ctrl.get_value() || '') : ''
        };
    }

    // ------------------------------------------------------------ layout

    make_layout(wrapper) {
        $(wrapper).find('.layout-main-section').html(`
            <style>
                .pm-grid2 { display:grid; grid-template-columns:1fr 1.5fr; gap:12px; margin-bottom:12px; }
                .pm-grid-eq { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
                .pm-table-wrap { max-height:320px; overflow:auto; }
                .pm-table { width:100%; border-collapse:collapse; font-size:12px; }
                .pm-table th { position:sticky; top:0; background:var(--card-bg); text-align:left;
                               padding:6px 8px; border-bottom:1px solid var(--border-color); }
                .pm-table td { padding:6px 8px; border-bottom:1px solid var(--border-color); }
                .pm-tabs { display:flex; gap:8px; margin-bottom:16px; }
                .pm-tab { padding:5px 14px; border:1px solid var(--border-color);
                          border-radius:6px; background:var(--card-bg); cursor:pointer; font-size:12px; }
                .pm-tab.active { background:#111; color:#fff; border-color:#111; }
                .pm-cards { display:grid; gap:12px; margin-bottom:12px; }
                .pm-cards.c5 { grid-template-columns:repeat(5,1fr); }
                .pm-cards.c4 { grid-template-columns:repeat(4,1fr); }
                .pm-cards.auto { grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
                .pm-card { background:var(--card-bg); border:1px solid var(--border-color);
                           border-radius:8px; padding:16px; }
                .pm-card .lbl { font-size:11px; color:var(--text-muted); margin-bottom:8px; }
                .pm-card .val { font-size:22px; font-weight:600; word-break:break-all; }
                .pm-chart-box { background:var(--card-bg); border:1px solid var(--border-color);
                                border-radius:8px; padding:16px; }
                .pm-chart-box .ttl { font-size:12px; margin-bottom:8px; }
                @media (max-width:900px){
                    .pm-grid2, .pm-grid-eq { grid-template-columns:1fr; }
                    .pm-cards.c5, .pm-cards.c4 { grid-template-columns:repeat(2,1fr); }
                }
            </style>
            <div class="pm-tabs"></div>
            <div class="pm-body"></div>
        `);
        this.$tabs = $(wrapper).find('.pm-tabs');
        this.$body = $(wrapper).find('.pm-body');

        Object.entries(this.tabs).forEach(([key, label]) => {
            $(`<div class="pm-tab" data-tab="${key}">${label}</div>`)
                .appendTo(this.$tabs)
                .on('click', () => { this.tab = key; this.load(); });
        });
    }

    // ------------------------------------------------------------ shared

    load() {
        this.$tabs.find('.pm-tab').removeClass('active')
            .filter(`[data-tab="${this.tab}"]`).addClass('active');

        if (this.tab === 'overview') return this.load_overview();
        if (this.tab === 'revenue') return this.load_revenue();
        if (this.tab === 'vacancy') return this.load_vacancy();
    }

    fetch(tab, render) {
        this.$body.html('<div class="text-muted" style="padding:40px;text-align:center">Loading...</div>');
        frappe.call({
            method: PM_API + 'get_dashboard',
            args: { tab: tab, ...this.filters() },
            callback: (r) => render(r.message || {})
        });
    }

    show_errors(d) {
        if (d.errors && Object.keys(d.errors).length) {
            frappe.msgprint({
                title: 'Dashboard query error',
                indicator: 'red',
                message: '<pre>' + frappe.utils.escape_html(JSON.stringify(d.errors, null, 2)) + '</pre>'
            });
        }
    }

    fmt(v) { return frappe.format(v || 0, { fieldtype: 'Float', precision: 0 }); }

    money(v) {
        return (parseFloat(v) || 0).toLocaleString(undefined,
            { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    card([l, v]) {
        return `<div class="pm-card"><div class="lbl">${frappe.utils.escape_html(l)}</div><div class="val">${v}</div></div>`;
    }

    table(heads, rows) {
        return `
            <div class="pm-table-wrap">
                <table class="pm-table">
                    <thead><tr>${heads.map(h => `<th>${h}</th>`).join('')}</tr></thead>
                    <tbody>${rows.join('') ||
                        `<tr><td colspan="${heads.length}" class="text-muted">No data</td></tr>`}</tbody>
                </table>
            </div>`;
    }

    // ------------------------------------------------------------ overview

    load_overview() { this.fetch('overview', (d) => this.render_overview(d)); }

    render_overview(d) {
        const s = d.summary || {};
        this.show_errors(d);

        const row1 = [
            ['Total Properties', this.fmt(s.total_properties)],
            ['Total Buildings', this.fmt(s.total_buildings)],
            ['Total Building Blocks', this.fmt(s.total_blocks)],
            ['Total Units', this.fmt(s.total_units)],
            ['Occupied Units', this.fmt(s.occupied_units)],
            ['Vacant Units', this.fmt(s.vacant_units)],
            ['Occupancy Rate %', this.fmt(s.occupancy_rate)]
        ];

        const alert_labels = {
            expiring_30d: 'Expiring 30d',
            awaiting_renewal: 'Awaiting Renewal',
            vacant_60d: 'Vacant 60d+',
            overdue_rent: 'Overdue Rent'
        };
        const counts = {};
        (d.alerts || []).forEach(a => { counts[a.alert_type] = a.alert_count; });
        const row2 = Object.keys(alert_labels).map(k => [alert_labels[k], this.fmt(counts[k])]);

        this.$body.html(`
            <div class="pm-cards auto">${row1.map(c => this.card(c)).join('')}</div>
            <div class="pm-cards auto">${row2.map(c => this.card(c)).join('')}</div>
            <div class="pm-grid-eq">
                <div class="pm-chart-box">
                    <div class="ttl">PM - Occupancy Rate % by Property</div>
                    <div id="pm-occ-chart"></div>
                </div>
                <div class="pm-chart-box">
                    <div class="ttl">PM - Occupied vs Vacant Units by Property</div>
                    <div id="pm-occ-compare"></div>
                </div>
            </div>
        `);

        const props = d.by_property || [];
        if (!props.length) return;
        const labels = props.map(p => p.property_name);
        const num = v => parseFloat(v) || 0;

        this.chart = new frappe.Chart('#pm-occ-chart', {
            type: 'bar',
            height: 280,
            colors: ['#2f8bdc'],
            data: {
                labels: labels,
                datasets: [{ name: 'Occupancy %', values: props.map(p => num(p.occupancy_rate)) }]
            },
            barOptions: { spaceRatio: 0.4 },
            tooltipOptions: { formatTooltipY: v => v + '%' }
        });

        new frappe.Chart('#pm-occ-compare', {
            type: 'bar',
            height: 280,
            colors: ['#22c55e', '#f59e0b'],
            data: {
                labels: labels,
                datasets: [
                    { name: 'Occupied', values: props.map(p => num(p.occupied_units)) },
                    { name: 'Vacant', values: props.map(p => num(p.vacant_units)) }
                ]
            },
            barOptions: { spaceRatio: 0.3 }
        });
    }

    // ------------------------------------------------------------ revenue

    load_revenue() { this.fetch('revenue', (d) => this.render_revenue(d)); }

    render_revenue(d) {
        const esc = frappe.utils.escape_html;
        const k = d.kpi || {};
        this.show_errors(d);

        const cards = [
            ['Monthly Rental Income', this.money(k.monthly_rental_income)],
            ['Annual Contract Value', this.money(k.annual_contract_value)],
            ['Outstanding Rent', this.money(k.outstanding_rent)],
            ['Collected This Month', this.money(k.collected_amount)],
            ['Collection Rate %', this.money(k.collection_rate)]
        ];

        const rows = (d.expiries || []).map(e => `
            <tr>
                <td>${esc(e.tenant_name || '')}</td>
                <td>${esc(e.property_name || '')}</td>
                <td>${esc(e.unit_name || '')}</td>
                <td>${esc(String(e.expiry_date || '').slice(0, 10))}</td>
                <td>${e.days_to_expiry ?? ''}</td>
                <td>${this.money(e.rent_amount)}</td>
            </tr>`);

        this.$body.html(`
            <div class="pm-cards c5">${cards.map(c => this.card(c)).join('')}</div>
            <div class="pm-grid2">
                <div class="pm-chart-box">
                    <div class="ttl">PM - Revenue Breakdown</div>
                    <div id="pm-rev-breakdown"></div>
                </div>
                <div class="pm-chart-box">
                    <div class="ttl">PM - Revenue Trend</div>
                    <div id="pm-rev-trend"></div>
                </div>
            </div>
            <div class="pm-chart-box" style="margin-bottom:12px">
                <div class="ttl">PM - Monthly Rent Due vs Collected vs Outstanding</div>
                <div id="pm-rev-monthly"></div>
            </div>
            <div class="pm-grid2">
                <div class="pm-chart-box">
                    <div class="ttl">PM - Upcoming Lease Expiries</div>
                    ${this.table(['Tenant', 'Property', 'Unit', 'Expiry Date', 'Days', 'Rent'], rows)}
                </div>
                <div class="pm-chart-box">
                    <div class="ttl">PM - Lease Expiry Calendar</div>
                    <div id="pm-expiry-cal"></div>
                </div>
            </div>
        `);

        const num = v => parseFloat(v) || 0;

        const bd = d.breakdown || [];
        if (bd.length) {
            new frappe.Chart('#pm-rev-breakdown', {
                type: 'donut',
                height: 280,
                colors: ['#2f8bdc', '#f472b6', '#22c55e', '#f59e0b', '#8b5cf6'],
                data: {
                    labels: bd.map(x => x.revenue_category),
                    datasets: [{ values: bd.map(x => num(x.revenue_amount)) }]
                }
            });
        }

        const tr = d.trend || [];
        if (tr.length) {
            new frappe.Chart('#pm-rev-trend', {
                type: 'line',
                height: 280,
                colors: ['#2f8bdc', '#f472b6'],
                data: {
                    labels: tr.map(x => String(x.period_month).slice(0, 10)),
                    datasets: [
                        { name: 'Revenue', values: tr.map(x => num(x.revenue_amount)) },
                        { name: 'Collected', values: tr.map(x => num(x.collected_amount)) }
                    ]
                },
                lineOptions: { dotSize: 3 }
            });
        }

        const mo = d.monthly || [];
        if (mo.length) {
            new frappe.Chart('#pm-rev-monthly', {
                type: 'bar',
                height: 300,
                colors: ['#2f8bdc', '#22c55e', '#f59e0b'],
                data: {
                    labels: mo.map(x => String(x.period_month).slice(0, 7)),
                    datasets: [
                        { name: 'Rent Due', values: mo.map(x => num(x.rent_due)) },
                        { name: 'Rent Collected', values: mo.map(x => num(x.collected_amount)) },
                        { name: 'Outstanding Rent', values: mo.map(x => num(x.rent_outstanding)) }
                    ]
                },
                barOptions: { spaceRatio: 0.3 }
            });
        }

        const cal = d.calendar || [];
        if (cal.length) {
            new frappe.Chart('#pm-expiry-cal', {
                type: 'bar',
                height: 280,
                colors: ['#2f8bdc'],
                data: {
                    labels: cal.map(x => String(x.expiry_month).slice(0, 10)),
                    datasets: [{ name: 'Expiries', values: cal.map(x => x.expiry_month_count || 0) }]
                },
                barOptions: { spaceRatio: 0.4 }
            });
        }
    }

    // ------------------------------------------------------------ vacancy

    load_vacancy() { this.fetch('vacancy', (d) => this.render_vacancy(d)); }

    render_vacancy(d) {
        const esc = frappe.utils.escape_html;
        this.show_errors(d);

        const vac = d.vacancy || [];
        const vacRows = vac.map(v => `
            <tr>
                <td>${esc(v.property_name || '')}</td>
                <td>${this.fmt(v.vacant_units)}</td>
                <td>${this.money(v.revenue_loss)}</td>
            </tr>`);

        // Split performance rows into top properties / bottom tenants
        const perf = d.performance || [];
        const norm = x => String(x || '').toLowerCase();
        const byType = t => perf.filter(r => norm(r.entity_type).includes(t));
        const num = r => parseFloat(r.metric_value) || 0;

        const pickTop = list => {
            const g = list.filter(r => norm(r.rank_group).includes('top'));
            return (g.length ? g : [...list].sort((a, b) => num(b) - num(a)).slice(0, 10));
        };
        const pickBottom = list => {
            const g = list.filter(r => norm(r.rank_group).includes('bottom'));
            return (g.length ? g : [...list].sort((a, b) => num(a) - num(b)).slice(0, 10));
        };
        const perfRows = list => list.map(r => `
            <tr>
                <td>${esc(r.entity_name || '')}</td>
                <td>${this.money(r.metric_value)}</td>
                <td>${this.fmt(r.unit_count)}</td>
            </tr>`);

        const topProps = pickTop(byType('propert')).sort((a, b) => num(b) - num(a));
        const bottomTenants = pickBottom(byType('tenant')).sort((a, b) => num(a) - num(b));

        this.$body.html(`
            <div class="pm-grid-eq">
                <div class="pm-chart-box">
                    <div class="ttl">PM - Vacancy Duration (units)</div>
                    <div id="pm-vac-duration"></div>
                </div>
                <div class="pm-chart-box">
                    <div class="ttl">PM - Estimated Revenue Loss by Property</div>
                    <div id="pm-vac-loss"></div>
                </div>
            </div>
            <div class="pm-chart-box" style="margin-bottom:12px">
                <div class="ttl">PM - Vacancy by Property</div>
                ${this.table(['Property', 'Vacant Units', 'Est. Revenue Loss'], vacRows)}
            </div>
            <div class="pm-grid-eq">
                <div class="pm-chart-box">
                    <div class="ttl">PM - Top Performing Properties</div>
                    ${this.table(['Entity', 'Metric Value', 'Units'], perfRows(topProps))}
                </div>
                <div class="pm-chart-box">
                    <div class="ttl">PM - Bottom Performing Tenants</div>
                    ${this.table(['Entity', 'Metric Value', 'Units'], perfRows(bottomTenants))}
                </div>
            </div>
        `);

        const dur = d.duration || [];
        if (dur.length) {
            new frappe.Chart('#pm-vac-duration', {
                type: 'bar',
                height: 260,
                colors: ['#2f8bdc'],
                data: {
                    labels: dur.map(x => x.bucket),
                    datasets: [{ name: 'Vacant units', values: dur.map(x => parseFloat(x.units) || 0) }]
                },
                barOptions: { spaceRatio: 0.4 }
            });
        }
        if (vac.length) {
            new frappe.Chart('#pm-vac-loss', {
                type: 'bar',
                height: 260,
                colors: ['#f43f5e'],
                data: {
                    labels: vac.map(x => x.property_name),
                    datasets: [{ name: 'Revenue loss', values: vac.map(x => parseFloat(x.revenue_loss) || 0) }]
                },
                barOptions: { spaceRatio: 0.4 }
            });
        }
    }
}
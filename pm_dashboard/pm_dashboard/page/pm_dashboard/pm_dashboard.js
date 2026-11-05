frappe.pages['pm-dashboard'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Property Management'),
        single_column: true
    });
    new PMDashboard(page, wrapper);
};

const PM_API = 'pm_dashboard.pm_dashboard.page.pm_dashboard.pm_dashboard.';

class PMDashboard {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.tab = 'overview';
        this.charts = [];
        this.request = 0;
        this.tabs = {
            overview: __('Overview'),
            revenue: __('Rent & Collections'),
            vacancy: __('Vacancy & Performance'),
            contract_value: __('Contracts Overview')
        };
        this.make_layout();
        this.make_filters();
        this.page.set_primary_action(__('Refresh'), () => this.load(), 'refresh');
        this.load();
    }

    make_layout() {
        $(this.wrapper).find('.layout-main-section').html(`
            <style>
                .pm-shell { --pm-gap: 14px; }
                .pm-filters { display:flex; flex-wrap:wrap; align-items:flex-end; gap:10px; padding:14px;
                    margin-bottom:14px; border:1px solid var(--border-color); border-radius:10px; background:var(--card-bg); }
                .pm-filter { min-width:145px; flex:1 1 145px; }
                .pm-filter .control-label { font-size:11px; color:var(--text-muted); }
                .pm-tabs { display:flex; flex-wrap:wrap; gap:7px; margin:0 0 16px; border-bottom:1px solid var(--border-color); }
                .pm-tab { appearance:none; border:0; border-bottom:2px solid transparent; border-radius:0;
                    background:transparent; color:var(--text-muted); padding:9px 13px; font-weight:600; }
                .pm-tab:hover { color:var(--text-color); }
                .pm-tab.active { border-bottom-color:var(--primary); color:var(--text-color); }
                .pm-cards { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:var(--pm-gap); margin-bottom:16px; }
                .pm-cards.pm-six { grid-template-columns:repeat(3,minmax(0,1fr)); }
                .pm-cards.pm-six { grid-template-columns:repeat(3,minmax(0,1fr)); }
                .pm-kpi { text-align:left; width:100%; min-width:0; min-height:100px; padding:13px 14px;
                    border:1px solid var(--border-color); border-radius:10px; background:var(--card-bg); color:var(--text-color);
                    transition:box-shadow .15s ease,border-color .15s ease,transform .15s ease; }
                .pm-kpi:hover,.pm-kpi:focus-visible { border-color:var(--primary); box-shadow:0 3px 12px rgba(0,0,0,.08); transform:translateY(-1px); outline:none; }
                .pm-kpi:disabled { cursor:not-allowed; opacity:.65; }
                .pm-kpi-label { display:flex; justify-content:space-between; gap:8px; align-items:center; color:var(--text-muted);
                    font-size:11px; font-weight:600; letter-spacing:.02em; text-transform:uppercase; }
                .pm-kpi-label .pm-open { opacity:0; font-size:14px; transition:opacity .15s; }
                .pm-kpi:hover .pm-open,.pm-kpi:focus-visible .pm-open { opacity:1; }
                .pm-kpi-value { margin:9px 0 4px; font-size:25px; line-height:1.15; font-weight:700; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
                .pm-kpi-subtitle { color:var(--text-muted); font-size:11px; line-height:1.35; }
                .pm-pill { display:inline-block; margin-left:5px; padding:2px 7px; border-radius:20px; font-size:10px;
                    font-weight:600; background:var(--subtle-fg); color:var(--text-muted); vertical-align:1px; }
                .pm-pill.warning { color:#9a6700; background:#fff4ce; }
                .pm-pill.lock { color:var(--text-muted); background:var(--subtle-fg); }
                .pm-section-title { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin:4px 0 10px; }
                .pm-section-title h4 { margin:0; font-size:14px; font-weight:650; }
                .pm-section-title span { color:var(--text-muted); font-size:11px; }
                .pm-grid-2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--pm-gap); margin-bottom:var(--pm-gap); }
                .pm-panel { min-width:0; margin-bottom:var(--pm-gap); padding:15px; border:1px solid var(--border-color);
                    border-radius:10px; background:var(--card-bg); }
                .pm-chart { min-height:220px; }
                .pm-table-scroll { width:100%; overflow:auto; max-height:410px; border:1px solid var(--border-color); border-radius:7px; }
                .pm-table { width:100%; border-collapse:separate; border-spacing:0; font-size:12px; white-space:nowrap; }
                .pm-table th { position:sticky; top:0; z-index:1; padding:8px 10px; text-align:left; color:var(--text-muted);
                    background:var(--subtle-fg); border-bottom:1px solid var(--border-color); font-size:10px; text-transform:uppercase; }
                .pm-table td { padding:8px 10px; border-bottom:1px solid var(--border-color); vertical-align:middle; }
                .pm-table tbody tr:last-child td { border-bottom:0; }
                .pm-table tbody tr:hover { background:var(--subtle-fg); }
                .pm-num { text-align:right; font-variant-numeric:tabular-nums; }
                .pm-callout { display:flex; align-items:flex-start; gap:10px; margin-bottom:14px; padding:12px 14px;
                    border:1px solid #f2d675; border-radius:9px; background:#fff9e6; color:#765b00; font-size:12px; }
                .pm-callout strong { display:block; margin-bottom:2px; }
                .pm-empty { padding:36px 14px; text-align:center; color:var(--text-muted); }
                .pm-loading { padding:48px 12px; text-align:center; color:var(--text-muted); }
                .pm-dialog .modal-dialog { width:min(1180px,96vw); max-width:1180px; }
                .pm-dialog .modal-content { border-radius:12px; overflow:hidden; }
                .pm-dialog-head { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:flex-start; gap:12px;
                    padding:17px 19px; border-bottom:1px solid var(--border-color); background:var(--subtle-fg); }
                .pm-dialog-head h3 { margin:0 0 4px; font-size:17px; font-weight:700; }
                .pm-dialog-meta { color:var(--text-muted); font-size:11px; line-height:1.6; }
                .pm-dialog-value { text-align:right; font-size:22px; font-weight:700; font-variant-numeric:tabular-nums; }
                .pm-dialog-unit { margin-top:2px; color:var(--text-muted); font-size:10px; text-align:right; }
                .pm-dialog-content { padding:15px 18px 18px; }
                .pm-recon { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:13px; }
                .pm-recon-item { min-width:135px; padding:9px 11px; border:1px solid var(--border-color); border-radius:8px; background:var(--card-bg); }
                .pm-recon-label { color:var(--text-muted); font-size:10px; }
                .pm-recon-value { margin-top:3px; font-size:13px; font-weight:650; font-variant-numeric:tabular-nums; }
                .pm-source-note { margin:0 0 12px; color:var(--text-muted); font-size:11px; }
                .pm-dialog-toolbar { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px; }
                .pm-dialog-pagination { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-top:11px; }
                .pm-dialog-pagination .btn { min-width:78px; }
                .pm-dialog-lock { margin:15px; padding:26px; text-align:center; border-radius:9px; background:var(--subtle-fg); }
                .pm-dialog-lock .icon { font-size:24px; margin-bottom:7px; }
                @media (max-width:1050px) { .pm-cards,.pm-cards.pm-six { grid-template-columns:repeat(2,minmax(0,1fr)); } }
                @media (max-width:700px) { .pm-grid-2 { grid-template-columns:1fr; } .pm-cards,.pm-cards.pm-six { grid-template-columns:1fr; }
                    .pm-kpi { min-height:96px; } .pm-dialog-value,.pm-dialog-unit { text-align:left; } }
            </style>
            <div class="pm-shell">
                <div class="pm-filters"></div>
                <div class="pm-tabs" role="tablist"></div>
                <div class="pm-body" aria-live="polite"></div>
            </div>
        `);
        this.$filters = $(this.wrapper).find('.pm-filters');
        this.$tabs = $(this.wrapper).find('.pm-tabs');
        this.$body = $(this.wrapper).find('.pm-body');

        Object.entries(this.tabs).forEach(([key, label]) => {
            $(`<button type="button" class="pm-tab" role="tab" data-tab="${key}"></button>`)
                .text(label)
                .appendTo(this.$tabs)
                .on('click', () => {
                    this.tab = key;
                    this.load();
                });
        });
    }

    make_filters() {
        this.options = {};
        this.load_debounced = frappe.utils.debounce(() => this.load(), 300);
        const make = (df) => {
            const $container = $('<div class="pm-filter"></div>').appendTo(this.$filters);
            const control = frappe.ui.form.make_control({ parent: $container, df, render_input: true });
            control.refresh();
            return control;
        };
        this.from = make({ fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date', change: () => this.load_debounced() });
        this.to = make({ fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date', change: () => this.load_debounced() });
        // No default date filters — start with no date range (all time)

        const narrow = (key) => () => {
            const values = (this.options[key] || []).map(row => row.value);
            return values.length ? { filters: { name: ['in', values] } } : { filters: { name: ['=', '__none__'] } };
        };
        const cascade = () => this.load_options(() => this.load_debounced());
        this.building = make({ fieldname: 'building', label: __('Building'), fieldtype: 'Link', options: 'Building', get_query: narrow('buildings'), change: cascade });
        this.block = make({ fieldname: 'building_block', label: __('Building Block'), fieldtype: 'Link', options: 'Building Block', get_query: narrow('building_blocks'), change: cascade });
        this.floor = make({ fieldname: 'floor', label: __('Floor'), fieldtype: 'Link', options: 'Floor', get_query: narrow('floors'), change: cascade });
        this.property = make({ fieldname: 'property', label: __('Property'), fieldtype: 'Link', options: 'Property', get_query: narrow('properties'), change: () => this.load_debounced() });

        $('<button type="button" class="btn btn-default btn-sm" style="margin-bottom:var(--margin-md,12px)"></button>')
            .text(__('Reset'))
            .appendTo(this.$filters)
            .on('click', () => {
                this.from.set_value('');
                this.to.set_value('');
                [this.building, this.block, this.floor, this.property].forEach(control => control.set_value(''));
                this.load_options(() => this.load());
            });
        this.load_options();
    }

    filters() {
        const from_date = this.from.get_value() || '';
        const to_date = this.to.get_value() || '';
        if (from_date && to_date && from_date > to_date) {
            return null;
        }
        return {
            from_date,
            to_date,
            building: this.building.get_value() || '',
            building_block: this.block.get_value() || '',
            floor: this.floor.get_value() || '',
            property: this.property.get_value() || ''
        };
    }

    load_options(done) {
        const filters = this.filters();
        if (!filters) return;
        frappe.call({
            method: PM_API + 'get_filter_options',
            args: {
                building: filters.building,
                building_block: filters.building_block,
                floor: filters.floor,
                property: filters.property
            },
            callback: (response) => {
                const options = response.message || {};
                this.options = options;
                const valid = (list, value) => !value || (list || []).some(item => String(item.value) === String(value));
                if (!valid(options.buildings, filters.building)) this.building.set_value('');
                if (!valid(options.building_blocks, filters.building_block)) this.block.set_value('');
                if (!valid(options.floors, filters.floor)) this.floor.set_value('');
                if (!valid(options.properties, filters.property)) this.property.set_value('');
                if (done) done();
            }
        });
    }

    load() {
        const filters = this.filters();
        if (!filters) {
            frappe.show_alert({ message: __('From Date cannot be after To Date.'), indicator: 'orange' });
            return;
        }
        this.$tabs.find('.pm-tab').removeClass('active').attr('aria-selected', 'false')
            .filter(`[data-tab="${this.tab}"]`).addClass('active').attr('aria-selected', 'true');
        const request = ++this.request;
        this.destroy_charts();
        this.$body.html(`<div class="pm-loading"><span class="fa fa-spinner fa-spin"></span> ${__('Loading dashboard…')}</div>`);
        frappe.call({
            method: PM_API + 'get_dashboard',
            args: { tab: this.tab, ...filters },
            callback: (response) => {
                if (request !== this.request) return;
                if (!response || !response.message) {
                    this.show_load_error(__('The server returned no dashboard data.'));
                    return;
                }
                const data = response.message;
                this.render(data);
            },
            error: (response) => {
                if (request !== this.request) return;
                console.error('PM Dashboard request failed', response);
                let message = response && response.message;
                if (!message && response && response.responseJSON) {
                    message = response.responseJSON.message;
                    if (!message && response.responseJSON._server_messages) {
                        try {
                            const messages = JSON.parse(response.responseJSON._server_messages);
                            message = messages.map(item => {
                                try { return JSON.parse(item).message; } catch (e) { return item; }
                            }).filter(Boolean).join(' ');
                        } catch (e) { /* use the generic message below */ }
                    }
                }
                this.show_load_error(message || __('Dashboard could not be loaded.'));
            }
        });
    }

    show_load_error(message) {
        const $panel = $(`<div class="pm-panel pm-empty text-danger"></div>`);
        $('<div></div>').text(message).appendTo($panel);
        $('<button type="button" class="btn btn-default btn-xs" style="margin-top:10px"></button>')
            .text(__('Retry'))
            .on('click', () => this.load())
            .appendTo($panel);
        this.$body.empty().append($panel);
    }

    render(data) {
        if (data.errors && Object.keys(data.errors).length) {
            console.warn('PM Dashboard source errors', data.errors);
        }
        const cardClass = this.tab === 'overview' ? 'pm-cards pm-six' : (this.tab === 'revenue' ? 'pm-cards pm-six' : 'pm-cards');
        const cards = (data.cards || []).map(card => this.card_html(card)).join('');
        let content = `<div class="${cardClass}">${cards || `<div class="pm-panel pm-empty">${__('No data available for these filters.')}</div>`}</div>`;
        if (this.tab === 'overview') content += this.render_overview(data);
        else if (this.tab === 'revenue') content += this.render_revenue(data);
        else if (this.tab === 'vacancy') content += this.render_vacancy(data);
        else if (this.tab === 'contract_value') content += this.render_contracts_overview(data);
        this.$body.html(content);
        this.bind_cards(data.cards || []);
        this.render_charts(data);
    }

    card_html(card) {
        const locked = card.permission && !card.permission.allowed;
        const status = card.status === 'data-gap'
            ? `<span class="pm-pill warning">${__('Data gap')}</span>`
            : locked ? `<span class="pm-pill lock">${__('Restricted')}</span>` : '';
        const value = locked ? __('Restricted') : this.format_value(card.value, card.unit);
        const subtitle = card.subtitle ? `<div class="pm-kpi-subtitle">${this.esc(card.subtitle)}</div>` : '';
        return `<button type="button" class="pm-kpi" data-kpi="${this.esc(card.key)}" aria-label="${this.esc(card.label)} ${this.esc(value)}">
            <div class="pm-kpi-label"><span>${this.esc(card.label)}${status}</span><span class="pm-open" aria-hidden="true">↗</span></div>
            <div class="pm-kpi-value">${this.esc(value)}</div>${subtitle}
        </button>`;
    }

    bind_cards(cards) {
        const byKey = Object.fromEntries(cards.map(card => [card.key, card]));
        const silent = new Set([
            "overview.total_area", "overview.occupied_area", "overview.occupancy_rate",
            "overview.area_occupancy_rate",
            "revenue.collection_rate", "vacancy.vacancy_rate", "vacancy.revenue_loss",
        ]);
        this.$body.find('.pm-kpi').on('click', (event) => {
            const card = byKey[$(event.currentTarget).attr('data-kpi')];
            if (card && !silent.has(card.key)) this.open_details(card);
        });
    }

    render_overview(data) {
        const summary = data.summary || {};
        return `
            <div class="pm-grid-2">
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Occupancy by Building')}</h4><span>${__('Unit count')}</span></div><div id="pm-chart-occupancy" class="pm-chart"></div></section>
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Occupied vs Vacant Units')}</h4><span>${__('Totals reconcile to the cards')}</span></div><div id="pm-chart-units" class="pm-chart"></div></section>
            </div>`;
    }

    render_revenue(data) {
        const months = (data.charts && data.charts.monthly) || [];
        const labels = months.map(m => moment(m.month).format('MMM YY'));
        return `
            <div class="pm-grid-2">
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Rental Income vs Invoiced Rent')}</h4><span>${__('Contract rent vs submitted invoices')}</span></div><div id="pm-chart-rent-trend" class="pm-chart"></div></section>
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Collected vs Outstanding')}</h4><span>${__('Invoice month; collection as of selected period')}</span></div><div id="pm-chart-rent-collections" class="pm-chart"></div></section>
            </div>`;
    }

    render_vacancy(data) {
        const summary = data.summary || {};
        const rows = data.tables && data.tables.vacant_properties || [];
        const rowData = rows.map(row => [
            row.property_label, row.building, row.building_block, row.floor,
            this.date(row.vacancy_start), row.days_vacant,
            this.money(row.potential_rent), this.money(row.revenue_loss),
            row.pre_booked ? __('Yes') : __('No'),
            row.missing_potential_rent ? __('Missing') : ''
        ]);
        const banner = summary.missing_potential_rent ? `
            <div class="pm-callout"><span class="fa fa-exclamation-triangle"></span><div>
                <strong>${__('Potential Rent is not populated for')} ${summary.missing_potential_rent} ${__('vacant units.')}</strong>
                ${__('Revenue Loss uses Property Potential Rent only; no last-contract fallback is applied.')}
            </div></div>` : '';
        return `${banner}
            <div class="pm-grid-2">
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Vacancy by Building')}</h4><span>${__('Count and rate')}</span></div><div id="pm-chart-vacancy" class="pm-chart"></div></section>
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Vacancy Duration')}</h4><span>${__('Buckets sum to vacant units')}</span></div><div id="pm-chart-vacancy-duration" class="pm-chart"></div></section>
            </div>
            <section class="pm-panel"><div class="pm-section-title"><h4>${__('Vacant Property Register')}</h4><span>${rows.length} ${__('units')}</span></div>
                ${this.table(['Unit', 'Building', 'Block', 'Floor', 'Start (Est.)', 'Days', 'Potential Rent', 'Loss', 'Pre-Booked', 'Data'], rowData)}</section>`;
    }

    render_contracts_overview(data) {
        const active = data.tables && data.tables.active_contracts || [];
        const awaiting = data.tables && data.tables.expiries || [];
        const prebooked = data.tables && data.tables.pre_booked || [];
        const activeRows = active.map(row => [
            row.tenant, row.property_label, row.building,
            this.money(row.monthly), this.date(row.start), this.date(row.end)
        ]);
        const awaitingRows = awaiting.map(row => [
            row.tenant, row.property_label, row.building,
            this.money(row.monthly), this.date(row.end_date), row.days_to_expiry
        ]);
        const prebookedRows = prebooked.map(row => [
            row.tenant, row.property_label, row.building,
            this.money(row.monthly), this.date(row.start), this.date(row.end)
        ]);
        return `
            <div class="pm-grid-2">
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Active Contract Register')}</h4><span>${active.length} ${__('contracts')}</span></div>
                    ${this.table(['Tenant', 'Unit', 'Building', 'Monthly Rent', 'Start', 'End'], activeRows)}</section>
                <section class="pm-panel"><div class="pm-section-title"><h4>${__('Awaiting Renewal')}</h4><span>${awaiting.length} ${__('expiring in next 30 days')}</span></div>
                    ${this.table(['Tenant', 'Unit', 'Building', 'Monthly Rent', 'End Date', 'Days Left'], awaitingRows)}</section>
            </div>
            <section class="pm-panel"><div class="pm-section-title"><h4>${__('Pre-Booked Contracts')}</h4><span>${prebooked.length} ${__('starting within 12 months')}</span></div>
                ${this.table(['Tenant', 'Unit', 'Building', 'Monthly Rent', 'Start', 'End'], prebookedRows)}</section>`;
    }

    render_charts(data) {
        if (this.tab === 'overview') {
            const summary = data.summary || {};
            const buildings = summary.buildings || [];
            this.make_chart('#pm-chart-occupancy', 'bar', ['#2f80ed'], buildings.map(b => b.building), [
                { name: __('Occupancy %'), values: buildings.map(b => this.number(b.occupancy_rate)) }
            ], { tooltipOptions: { formatTooltipY: value => `${value}%` } });
            this.make_chart('#pm-chart-units', 'bar', ['#22a06b', '#e9a23b'], buildings.map(b => b.building), [
                { name: __('Occupied'), values: buildings.map(b => this.number(b.occupied_units)) },
                { name: __('Vacant'), values: buildings.map(b => this.number(b.vacant_units)) }
            ]);
        } else if (this.tab === 'revenue') {
            // Rental income (contract monthly rent), invoiced rent, collected, outstanding per month.
            const monthly = data.charts && data.charts.monthly || [];
            if (monthly.length) {
                const labels = monthly.map(m => moment(m.month).format('MMM YY'));
                this.make_chart('#pm-chart-rent-trend', 'line', ['#2f80ed', '#26a69a'], labels, [
                    { name: __('Rental Income'), values: monthly.map(m => this.number(m.rental_income)) },
                    { name: __('Invoiced Rent'), values: monthly.map(m => this.number(m.invoiced_rent)) }
                ], { lineOptions: { dotSize: 3 } });
                this.make_chart('#pm-chart-rent-collections', 'bar', ['#22a06b', '#d9534f'], labels, [
                    { name: __('Collected'), values: monthly.map(m => this.number(m.collected)) },
                    { name: __('Outstanding'), values: monthly.map(m => this.number(m.outstanding)) }
                ], { barOptions: { spaceRatio: .35 } });
            }
        } else if (this.tab === 'vacancy') {
            const summary = data.summary || {};
            const rows = data.charts && data.charts.by_building || [];
            if (rows.length) {
                this.make_chart('#pm-chart-vacancy', 'bar', ['#ef8f35'], rows.map(r => r.building), [
                    { name: __('Vacant units'), values: rows.map(r => this.number(r.vacant_units)) }
                ]);
            }
            const duration = data.charts && data.charts.duration || [];
            if (duration.length) this.make_chart('#pm-chart-vacancy-duration', 'bar', ['#e9a23b'], duration.map(r => r.bucket), [
                { name: __('Units'), values: duration.map(r => this.number(r.units)) }
            ]);
        }
    }

    make_chart(selector, type, colors, labels, datasets, options = {}) {
        const element = this.$body.find(selector)[0];
        if (!element) return;
        const $el = $(element);
        if (!$el.is(':visible') || $el.width() <= 0 || !labels || !labels.length) return;
        const safeLabels = labels.map(v => (v == null ? '' : String(v)));
        const safeDatasets = (datasets || []).map(ds => ({
            ...ds,
            values: (ds.values || []).map(v => {
                const n = Number(v);
                return isFinite(n) ? n : 0;
            }),
        }));
        try {
            const chart = new frappe.Chart(element, {
                type,
                height: 250,
                colors,
                data: { labels: safeLabels, datasets: safeDatasets },
                tooltipOptions: {
                    formatTooltipY: value => `${Number(value || 0)}`,
                },
                ...options,
            });
            this.charts.push(chart);
        } catch (error) {
            console.error('PM Dashboard chart render failed', error);
            $(element).html(`<div class="pm-empty">${__('Chart unavailable')}</div>`);
        }
    }

    destroy_charts() {
        this.charts.forEach(chart => {
            try { chart.destroy(); } catch (e) { /* chart may already be removed */ }
        });
        this.charts = [];
    }

    async open_details(card) {
        const dialog = new frappe.ui.Dialog({
            title: __('KPI details'),
            size: 'extra-large',
            fields: [{ fieldtype: 'HTML', fieldname: 'content' }],
            primary_action_label: __('Close'),
            primary_action: () => { document.activeElement?.blur(); dialog.hide(); }
        });
        dialog.$wrapper.addClass('pm-dialog');
        const $content = dialog.fields_dict.content.$wrapper;
        let currentPage = 1;
        let pageSize = 25;
        let requestId = 0;
        const loadPage = (page) => {
            const id = ++requestId;
            currentPage = page;
            $content.html(`<div class="pm-loading"><span class="fa fa-spinner fa-spin"></span> ${__('Loading details…')}</div>`);
            frappe.call({
                method: PM_API + 'get_kpi_details',
                args: { kpi: card.key, page, page_size: pageSize, ...this.filters() },
                callback: (response) => {
                    if (id !== requestId) return;
                    const details = response.message || {};
                    $content.html(this.details_html(card, details));
                    $content.find('[data-page]').on('click', (event) => {
                        const next = parseInt($(event.currentTarget).attr('data-page'), 10);
                        if (next > 0 && next !== currentPage) loadPage(next);
                    });
                    $content.find('[data-page-size]').on('change', (event) => {
                        pageSize = parseInt($(event.currentTarget).val(), 10) || 25;
                        loadPage(1);
                    });
                    $content.find('[data-open-doctype]').on('click', (event) => {
                        const $target = $(event.currentTarget);
                        const doctype = $target.attr('data-open-doctype');
                        const name = $target.attr('data-open-name');
                        if (doctype && name) {
                            document.activeElement?.blur();
                            dialog.hide();
                            frappe.set_route('Form', doctype, name);
                        }
                    });
                },
                error: () => {
                    if (id !== requestId) return;
                    $content.html(`<div class="pm-dialog-lock text-danger">${__('Could not load this KPI detail. Close and retry.')}</div>`);
                }
            });
        };
        dialog.show();
        loadPage(1);
    }

    details_html(card, details) {
        if (details.permission && !details.permission.allowed) {
            return `<div class="pm-dialog-lock"><div class="fa fa-lock"></div><strong>${__('Access restricted')}</strong>
                <div class="text-muted">${__('Read permission is required for')} ${this.esc(details.permission.doctype || card.source_doctype)}.</div></div>`;
        }
        const value = this.format_value(card.value, card.unit);
        const period = details.period || {};
        const chips = [
            period.from_date && `${__('From')} ${this.date(period.from_date)}`,
            period.to_date && `${__('To')} ${this.date(period.to_date)}`,
            period.as_of && `${__('As of')} ${this.date(period.as_of)}`
        ].filter(Boolean).map(value => `<span class="pm-pill">${this.esc(value)}</span>`);
        const chips_html = Array.isArray(chips) ? chips.join(' ') : String(chips || '');
        const reconciliation = (details.reconciliation || []).map(item => `
            <div class="pm-recon-item"><div class="pm-recon-label">${this.esc(item.sign ? `${item.sign} ${item.label}` : item.label)}</div>
                <div class="pm-recon-value">${this.esc(this.format_value(item.amount, item.unit || (typeof item.amount === 'number' && item.amount % 1 !== 0 ? 'money' : 'number')))}</div></div>`).join('');
        const rows = details.rows || [];
        const columns = details.columns || [];
        const bodyRows = rows.map(row => `<tr>${columns.map(column => `<td class="${['money','number','percent'].includes(column.type) ? 'pm-num' : ''}">${this.cell(row, column)}</td>`).join('')}</tr>`);
        const table = rows.length ? `<div class="pm-table-scroll"><table class="pm-table"><thead><tr>${columns.map(column => `<th class="${['money','number','percent'].includes(column.type) ? 'pm-num' : ''}">${this.esc(column.label)}</th>`).join('')}</tr></thead><tbody>${bodyRows.join('')}</tbody></table></div>`
            : `<div class="pm-empty">${__('No source rows for the selected filters.')}</div>`;
        const page = details.page || 1;
        const pageSize = details.page_size || 25;
        const pages = details.total_pages || 1;
        const pagination = `
            <div class="pm-dialog-pagination">
                <div class="text-muted">${__('Rows')} ${details.total ? (page - 1) * pageSize + 1 : 0}–${Math.min(page * pageSize, details.total || 0)} ${__('of')} ${details.total || 0}</div>
                <div style="display:flex;align-items:center;gap:7px">
                    <select class="form-control input-xs" data-page-size style="width:75px">
                        ${[25, 50, 100].map(size => `<option value="${size}" ${size === pageSize ? 'selected' : ''}>${size}</option>`).join('')}
                    </select>
                    <button type="button" class="btn btn-default btn-xs" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>${__('Previous')}</button>
                    <span class="text-muted">${page} / ${pages}</span>
                    <button type="button" class="btn btn-default btn-xs" data-page="${page + 1}" ${page >= pages ? 'disabled' : ''}>${__('Next')}</button>
                </div>
            </div>`;
        const totalText = this.format_totals(details.totals || {});
        return `<div class="pm-dialog-head">
                <div><h3>${this.esc(card.label)}</h3><div class="pm-dialog-meta">${chips_html}</div></div>
                <div><div class="pm-dialog-value">${this.esc(value)}</div><div class="pm-dialog-unit">${this.esc(card.unit === 'money' ? 'KWD' : card.unit === 'percent' ? '%' : '')}</div></div>
            </div>
            <div class="pm-dialog-content">
                ${reconciliation ? `<div class="pm-recon">${reconciliation}</div>` : ''}
                <p class="pm-source-note">${totalText ? this.esc(totalText) : ''}</p>
                <div class="pm-dialog-toolbar"><span class="text-muted">${__('Underlying records')}</span><span class="text-muted">${this.esc(details.permission && details.permission.doctype || card.source_doctype || '')}</span></div>
                ${table}${pagination}
            </div>`;
    }

    cell(row, column) {
        const value = row[column.key];
        const link = row._links && row._links[column.key];
        if (link && value) {
            return `<button type="button" class="btn btn-link btn-xs" data-open-doctype="${this.esc(link.doctype)}" data-open-name="${this.esc(link.name)}">${this.esc(value)}</button>`;
        }
        if (column.type === 'money') return this.esc(this.money(value));
        if (column.type === 'percent') return this.esc(`${this.money(value)}%`);
        if (column.type === 'date') return this.esc(this.date(value));
        if (column.type === 'boolean') return this.esc(value ? __('Yes') : __('No'));
        if (column.type === 'number') return this.esc(this.number_format(value));
        if (Array.isArray(value)) return this.esc(value.join(', '));
        return this.esc(value == null ? '' : String(value));
    }

    format_totals(totals) {
        const entries = Object.entries(totals).filter(([, value]) => typeof value === 'number');
        return entries.slice(0, 3).map(([key, value]) => `${this.label(key)} ${this.money(value)}`).join(' · ');
    }

    format_value(value, unit) {
        if (value === null || value === undefined) return __('Unavailable');
        if (unit === 'money') return this.money(value);
        if (unit === 'percent') return `${this.money(value)}%`;
        if (unit === 'area') return this.money(value);
        return this.number_format(value);
    }

    money(value) {
        return (Number(value) || 0).toLocaleString('en-KW', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    number_format(value) {
        return (Number(value) || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
    }

    number(value) { return Number(value) || 0; }

    date(value) {
        if (!value) return '—';
        const parsed = moment(value);
        return parsed.isValid() ? parsed.format('DD MMM YYYY') : this.esc(value);
    }

    label(value) {
        return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    }

    esc(value) { return frappe.utils.escape_html(String(value == null ? '' : value)); }

    table(headers, rows) {
        if (!rows || !rows.length) return `<div class="pm-empty">${__('No records for the selected filters.')}</div>`;
        return `<div class="pm-table-scroll"><table class="pm-table"><thead><tr>${headers.map(item => `<th>${this.esc(item)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map(row => `<tr>${row.map(value => `<td>${this.esc(value == null ? '' : value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
}

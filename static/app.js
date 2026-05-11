function dashboard() {
  return {
    races: [],
    summary: { total: 0, by_label: {}, by_category: {}, by_country: {}, by_month: {}, countries: [], labels: [], categories: [] },
    filters: { month: "", country: "", label: "", category: "" },
    search: "",
    view: "grid",
    reports: [],
    scraperStatus: { coverage_pct: 0, implemented: [], total_races: 0 },
    genMonth: "2026-03",
    generating: false,
    genMessage: "",
    charts: { month: null, category: null },

    async init() {
      await Promise.all([this.loadRaces(), this.loadReports(), this.loadScraperStatus()]);
      this.$nextTick(() => this.renderCharts());
    },

    async loadRaces() {
      const r = await fetch("/api/races").then(r => r.json());
      this.races = r.races;
      this.summary = r.summary;
    },

    async loadReports() {
      this.reports = await fetch("/api/reports").then(r => r.json());
    },

    async loadScraperStatus() {
      this.scraperStatus = await fetch("/api/scrapers").then(r => r.json());
    },

    async generate() {
      if (!this.genMonth) return;
      this.generating = true;
      this.genMessage = "";
      try {
        const r = await fetch(`/api/reports/generate?month=${encodeURIComponent(this.genMonth)}`, { method: "POST" });
        if (!r.ok) {
          this.genMessage = `Failed: ${(await r.json()).detail || r.status}`;
        } else {
          const j = await r.json();
          this.genMessage = `Generated ${j.file}`;
          await this.loadReports();
        }
      } catch (e) {
        this.genMessage = `Error: ${e.message}`;
      } finally {
        this.generating = false;
      }
    },

    get filtered() {
      const q = this.search.trim().toLowerCase();
      return this.races.filter(r => {
        if (this.filters.month && String(r.month) !== String(this.filters.month)) return false;
        if (this.filters.country && r.country !== this.filters.country) return false;
        if (this.filters.label && r.label !== this.filters.label) return false;
        if (this.filters.category && r.category !== this.filters.category) return false;
        if (q && !(r.name.toLowerCase().includes(q) || r.venue.toLowerCase().includes(q))) return false;
        return true;
      });
    },

    get groupedByMonth() {
      const groups = {};
      for (const r of this.filtered) {
        groups[r.month] = groups[r.month] || { month: r.month, items: [] };
        groups[r.month].items.push(r);
      }
      return Object.values(groups).sort((a, b) => a.month - b.month);
    },

    get kpis() {
      const platinum = this.summary.by_label?.Platinum || 0;
      const countries = (this.summary.countries || []).length;
      const now = new Date();
      const thisMonth = this.races.filter(r => r.month === now.getMonth() + 1 && r.year === now.getFullYear()).length;
      const total = this.summary.total || 0;
      return [
        { label: "Total races", value: total, hint: "2026 season", tone: "text-slate-500" },
        { label: "Countries", value: countries, hint: "global footprint", tone: "text-indigo-600" },
        { label: "Platinum races", value: platinum, hint: "World Athletics top tier", tone: "text-rose-600" },
        { label: "This month", value: thisMonth, hint: "events", tone: "text-emerald-600" },
      ];
    },

    clearFilters() {
      this.filters = { month: "", country: "", label: "", category: "" };
      this.search = "";
    },

    monthName(m) {
      return ["January","February","March","April","May","June","July","August","September","October","November","December"][m - 1];
    },
    monthShort(m) {
      return ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"][m - 1];
    },
    dayOf(iso) { return new Date(iso).getDate(); },
    formatDate(iso) {
      try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
      catch { return iso; }
    },

    labelPill(label) {
      switch (label) {
        case "Platinum": return "bg-violet-100 text-violet-700 ring-1 ring-violet-200";
        case "Gold":     return "bg-amber-100 text-amber-700 ring-1 ring-amber-200";
        case "Elite":    return "bg-sky-100 text-sky-700 ring-1 ring-sky-200";
        case "Label":    return "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200";
        default:         return "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
      }
    },
    labelStripe(label) {
      switch (label) {
        case "Platinum": return "bg-gradient-to-r from-violet-500 to-fuchsia-500";
        case "Gold":     return "bg-gradient-to-r from-amber-400 to-orange-500";
        case "Elite":    return "bg-gradient-to-r from-sky-400 to-blue-600";
        case "Label":    return "bg-gradient-to-r from-emerald-400 to-teal-600";
        default:         return "bg-slate-300";
      }
    },

    renderCharts() {
      const months = Array.from({ length: 12 }, (_, i) => this.summary.by_month?.[i + 1] || 0);
      const ctxM = document.getElementById("chart-month");
      if (ctxM && !this.charts.month) {
        this.charts.month = new Chart(ctxM, {
          type: "bar",
          data: {
            labels: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
            datasets: [{
              data: months,
              backgroundColor: ctx => {
                const c = ctx.chart.ctx.createLinearGradient(0, 0, 0, 200);
                c.addColorStop(0, "rgba(99,102,241,0.95)");
                c.addColorStop(1, "rgba(244,63,94,0.7)");
                return c;
              },
              borderRadius: 8,
              borderSkipped: false,
              maxBarThickness: 38,
            }],
          },
          options: {
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: "#64748b" } },
              y: { grid: { color: "#e2e8f0" }, ticks: { stepSize: 2, color: "#64748b" }, beginAtZero: true },
            },
          },
        });
      }

      const cats = this.summary.by_category || {};
      const ctxC = document.getElementById("chart-category");
      if (ctxC && !this.charts.category) {
        this.charts.category = new Chart(ctxC, {
          type: "doughnut",
          data: {
            labels: Object.keys(cats),
            datasets: [{
              data: Object.values(cats),
              backgroundColor: ["#4f46e5", "#e11d48", "#0ea5e9", "#10b981", "#f59e0b"],
              borderWidth: 0,
              hoverOffset: 6,
            }],
          },
          options: {
            cutout: "65%",
            plugins: {
              legend: { position: "bottom", labels: { color: "#475569", boxWidth: 8, boxHeight: 8, usePointStyle: true } },
            },
          },
        });
      }
    },
  };
}

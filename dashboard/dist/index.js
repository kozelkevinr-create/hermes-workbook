(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !SDK.React || !SDK.hooks) {
    return;
  }

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;

  var PLUGIN_NAME = "hermes-workbook";
  var API_ROOT = "/api/plugins/" + PLUGIN_NAME;
  var SCOPE_FILTERS = [
    { value: "", label: "All" },
    { value: "profile", label: "Profile (private)" },
    { value: "global", label: "Shared (global)" }
  ];

  function api(path) {
    return SDK.fetchJSON(API_ROOT + path);
  }

  function describeError(err) {
    var message = err && err.message ? String(err.message) : "Request failed";
    return message.length > 300 ? message.slice(0, 300) + "..." : message;
  }

  function columnLabel(index) {
    var label = "";
    var n = index + 1;
    while (n > 0) {
      var rem = (n - 1) % 26;
      label = String.fromCharCode(65 + rem) + label;
      n = Math.floor((n - 1) / 26);
    }
    return label;
  }

  function cellText(value) {
    if (value === null || value === undefined) {
      return "";
    }
    return String(value);
  }

  function query(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      if (params[key]) {
        parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
      }
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  function sharedStoreText(status) {
    var store = status && status.shared_store;
    if (!store) {
      return "Shared store status unavailable.";
    }
    if (!store.ok) {
      return "Shared store problem: " + cellText(store.detail);
    }
    if (store.shared === true) {
      return "Global scope is shared across profiles (" + store.peers_seen.length + " other profile(s) seen).";
    }
    return "Global scope is writable; no other profile has been seen yet.";
  }

  function WorkbookPage() {
    var scopeState = useState("");
    var scope = scopeState[0];
    var setScope = scopeState[1];
    var listState = useState({ loading: true, error: "", items: [] });
    var list = listState[0];
    var setList = listState[1];
    var statusState = useState(null);
    var status = statusState[0];
    var setStatus = statusState[1];
    var selectedState = useState(null);
    var selected = selectedState[0];
    var setSelected = selectedState[1];
    var sheetsState = useState({ loading: false, error: "", names: [], active: "" });
    var sheets = sheetsState[0];
    var setSheets = sheetsState[1];
    var dataState = useState({ loading: false, error: "", rows: [], truncated: false });
    var data = dataState[0];
    var setData = dataState[1];
    var reloadState = useState(0);
    var reload = reloadState[0];
    var setReload = reloadState[1];

    useEffect(
      function () {
        var cancelled = false;
        setList({ loading: true, error: "", items: [] });
        api("/workbooks" + query({ scope: scope }))
          .then(function (res) {
            if (!cancelled) {
              setList({ loading: false, error: "", items: res.workbooks || [] });
            }
          })
          .catch(function (err) {
            if (!cancelled) {
              setList({ loading: false, error: describeError(err), items: [] });
            }
          });
        api("/status")
          .then(function (res) {
            if (!cancelled) {
              setStatus(res);
            }
          })
          .catch(function () {
            if (!cancelled) {
              setStatus(null);
            }
          });
        return function () {
          cancelled = true;
        };
      },
      [scope, reload]
    );

    useEffect(
      function () {
        if (!selected) {
          return undefined;
        }
        var cancelled = false;
        setSheets({ loading: true, error: "", names: [], active: "" });
        setData({ loading: false, error: "", rows: [], truncated: false });
        api("/workbooks/" + encodeURIComponent(selected.name) + "/sheets" + query({ scope: selected.scope }))
          .then(function (res) {
            if (!cancelled) {
              var names = res.sheets || [];
              setSheets({ loading: false, error: "", names: names, active: names[0] || "" });
            }
          })
          .catch(function (err) {
            if (!cancelled) {
              setSheets({ loading: false, error: describeError(err), names: [], active: "" });
            }
          });
        return function () {
          cancelled = true;
        };
      },
      [selected, reload]
    );

    useEffect(
      function () {
        if (!selected || !sheets.active) {
          return undefined;
        }
        var cancelled = false;
        setData({ loading: true, error: "", rows: [], truncated: false });
        api(
          "/workbooks/" +
            encodeURIComponent(selected.name) +
            "/data" +
            query({ scope: selected.scope, sheet: sheets.active })
        )
          .then(function (res) {
            if (!cancelled) {
              setData({ loading: false, error: "", rows: res.rows || [], truncated: !!res.truncated });
            }
          })
          .catch(function (err) {
            if (!cancelled) {
              setData({ loading: false, error: describeError(err), rows: [], truncated: false });
            }
          });
        return function () {
          cancelled = true;
        };
      },
      [selected, sheets.active]
    );

    function renderScopeSwitch() {
      return h(
        "div",
        { className: "hw-scope-switch", role: "group", "aria-label": "Scope filter" },
        SCOPE_FILTERS.map(function (option) {
          return h(
            "button",
            {
              key: option.value || "all",
              type: "button",
              className: "hw-button" + (scope === option.value ? " hw-active" : ""),
              "aria-pressed": scope === option.value,
              onClick: function () {
                setScope(option.value);
                setSelected(null);
              }
            },
            option.label
          );
        })
      );
    }

    function renderList() {
      if (list.loading) {
        return h("p", { className: "hw-hint" }, "Loading workbooks...");
      }
      if (list.error) {
        return h("p", { className: "hw-error", role: "alert" }, list.error);
      }
      if (!list.items.length) {
        return h(
          "p",
          { className: "hw-hint" },
          "No workbooks registered yet. Ask an agent to create one with the workbook tools."
        );
      }
      return h(
        "ul",
        { className: "hw-list" },
        list.items.map(function (item) {
          var isSelected = selected && selected.name === item.name && selected.scope === item.scope;
          return h(
            "li",
            { key: item.scope + ":" + item.name },
            h(
              "button",
              {
                type: "button",
                className: "hw-item" + (isSelected ? " hw-active" : ""),
                "aria-pressed": !!isSelected,
                onClick: function () {
                  setSelected({ name: item.name, scope: item.scope });
                }
              },
              h("span", { className: "hw-item-name" }, item.name),
              h("span", { className: "hw-badge hw-badge-" + item.scope }, item.scope),
              h("span", { className: "hw-item-file" }, item.file + (item.exists ? "" : " (missing)"))
            )
          );
        })
      );
    }

    function renderTable() {
      if (data.loading) {
        return h("p", { className: "hw-hint" }, "Loading cells...");
      }
      if (data.error) {
        return h("p", { className: "hw-error", role: "alert" }, data.error);
      }
      if (!data.rows.length) {
        return h("p", { className: "hw-hint" }, "This sheet is empty.");
      }
      var width = 0;
      data.rows.forEach(function (row) {
        width = Math.max(width, row.length);
      });
      var headCells = [h("th", { key: "corner", className: "hw-corner" }, "")];
      for (var c = 0; c < width; c++) {
        headCells.push(h("th", { key: "c" + c, scope: "col" }, columnLabel(c)));
      }
      var body = data.rows.map(function (row, r) {
        var cells = [h("th", { key: "n", scope: "row", className: "hw-rownum" }, String(r + 1))];
        for (var i = 0; i < width; i++) {
          cells.push(h("td", { key: "c" + i }, cellText(row[i])));
        }
        return h("tr", { key: "r" + r }, cells);
      });
      return h(
        "div",
        { className: "hw-table-wrap" },
        h("table", { className: "hw-table" }, h("thead", null, h("tr", null, headCells)), h("tbody", null, body)),
        data.truncated
          ? h("p", { className: "hw-hint" }, "Showing the first rows only; the sheet is larger than the display limit.")
          : null
      );
    }

    function renderViewer() {
      if (!selected) {
        return h("p", { className: "hw-hint" }, "Select a workbook to review its sheets.");
      }
      if (sheets.loading) {
        return h("p", { className: "hw-hint" }, "Opening workbook...");
      }
      if (sheets.error) {
        return h("p", { className: "hw-error", role: "alert" }, sheets.error);
      }
      return h(
        "div",
        null,
        h("h2", { className: "hw-card-title" }, selected.name),
        h(
          "div",
          { className: "hw-tabs", role: "tablist", "aria-label": "Sheets" },
          sheets.names.map(function (name) {
            return h(
              "button",
              {
                key: name,
                type: "button",
                role: "tab",
                "aria-selected": sheets.active === name,
                className: "hw-button" + (sheets.active === name ? " hw-active" : ""),
                onClick: function () {
                  setSheets({ loading: false, error: "", names: sheets.names, active: name });
                }
              },
              name
            );
          })
        ),
        renderTable()
      );
    }

    return h(
      "div",
      { className: "hw-root" },
      h(
        "div",
        { className: "hw-header" },
        h("h1", { className: "hw-title" }, "Workbooks"),
        renderScopeSwitch(),
        h(
          "button",
          {
            type: "button",
            className: "hw-button",
            onClick: function () {
              setReload(reload + 1);
            }
          },
          "Refresh"
        )
      ),
      h("p", { className: "hw-hint", "aria-live": "polite" }, sharedStoreText(status)),
      h(
        "div",
        { className: "hw-layout" },
        h("section", { className: "hw-card", "aria-label": "Registered workbooks" }, renderList()),
        h("section", { className: "hw-card hw-viewer", "aria-label": "Workbook viewer" }, renderViewer())
      )
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN_NAME, WorkbookPage);
})();


(() => {
    "use strict";

    const sessionId = window.VOICELAB_REPLAY_SESSION_ID;

    const $ = id => document.getElementById(id);

    function esc(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function stateFromPayload(payload) {
        return payload?.state || payload?.research || payload || {};
    }

    function operationLabel(op) {
        return op?.symbol || op?.id || "Operation";
    }

    function renderOperations(operations) {
        const root = $("operations-list");

        if (!Array.isArray(operations) || !operations.length) {
            root.innerHTML = '<div class="empty">No symmetry operations persisted.</div>';
            return;
        }

        const verified = operations.filter(
            op => op?.verified === true ||
                  op?.verification?.status === "PASS"
        ).length;

        $("operation-badge").textContent =
            `${verified}/${operations.length} verified`;

        root.innerHTML = operations.map(op => {
            const ok =
                op?.verified === true ||
                op?.verification?.status === "PASS";

            return `
                <div class="operation">
                    <span class="operation-symbol">${esc(operationLabel(op))}</span>
                    <span class="${ok ? "pass" : "fail"}">
                        ${ok ? "✓ VERIFIED" : "✗ FAILED"}
                    </span>
                </div>
            `;
        }).join("");
    }

    function renderCharacters(state) {
        const root = $("characters");

        const characters =
            state?.characters ||
            state?.representation?.characters ||
            state?.group_theory?.reducible_characters ||
            {};

        const entries = Object.entries(characters);

        if (!entries.length) {
            root.innerHTML = '<div class="empty">No character data persisted.</div>';
            return;
        }

        root.innerHTML = entries.map(([label, value]) => `
            <div class="character">
                <span>${esc(label)}</span>
                <strong>${esc(value)}</strong>
            </div>
        `).join("");
    }

    function renderReduction(state) {
        const reduction = state?.group_theory?.reduction || {};
        const multiplicities = reduction?.multiplicities || {};

        const prettyIrrep = {
            "A1'": "A₁′",
            "A2'": "A₂′",
            "E'": "E′",
            "A1''": "A₁″",
            "A2''": "A₂″",
            "E''": "E″"
        };

        const terms = Object.entries(multiplicities)
            .filter(([, value]) => Number(value) !== 0)
            .map(([irrep, value]) => {
                const pretty = prettyIrrep[irrep] || irrep;
                return Number(value) === 1
                    ? pretty
                    : `${value}${pretty}`;
            });

        $("reduction-summary").textContent =
            terms.length
                ? `Γ(x,y,z) = ${terms.join(" + ")}`
                : "Γ(x,y,z) = —";
        const multRoot = $("multiplicities");

        multRoot.innerHTML = Object.entries(multiplicities).map(
            ([irrep, value]) => `
                <div class="multiplicity">
                    <span>${esc(irrep)}</span>
                    <strong>${esc(value)}</strong>
                </div>
            `
        ).join("");

        const basis = reduction?.irrep_basis_functions || {};
        const basisRoot = $("basis-functions");

        const basisEntries = Object.entries(basis);

        basisRoot.innerHTML = basisEntries.length
            ? "<b>Basis functions:</b> " +
              basisEntries.map(([irrep, funcs]) =>
                  `${esc(irrep)}: ${esc(Array.isArray(funcs) ? funcs.join(", ") : funcs)}`
              ).join(" · ")
            : "";
    }

    function renderVerification(state) {
        const verification =
            state?.verification ||
            state?.symmetry_verification ||
            {};

        const status = String(verification?.status || "").toUpperCase();

        $("verification-value").textContent =
            status || "WAITING";

        $("verification-badge").textContent =
            status || "WAITING";

        const root = $("verification-checks");
        const checks = verification?.checks || {};

        if (!Object.keys(checks).length) {
            root.innerHTML =
                '<div class="empty">No verification audit persisted.</div>';
            return;
        }

        root.innerHTML = Object.entries(checks).map(([name, value]) => {
            const ok = String(value).toUpperCase() === "PASS";
            const label = name
                .replaceAll("_", " ")
                .replace(/\b\w/g, c => c.toUpperCase());

            return `
                <div class="verification-item">
                    <span>${esc(label)}</span>
                    <strong class="${ok ? "pass" : "fail"}">
                        ${ok ? "✓ PASS" : "✗ FAIL"}
                    </strong>
                </div>
            `;
        }).join("");
    }

    function timelineTitle(event) {
        const changed = event?.payload?.changed;

        if (event?.event_type === "session_created")
            return "Research session created";

        if (event?.event_type === "memory_append") {
            const memory = event?.payload?.state?.memory;
            const last = Array.isArray(memory) ? memory.at(-1) : null;

            if (last?.kind === "typed")
                return "User research command recorded";

            return "Research memory updated";
        }

        if (event?.event_type === "state_update") {
            if (Array.isArray(changed)) {
                if (changed.includes("operations"))
                    return "Symmetry operations identified";

                if (changed.includes("matrices"))
                    return "Transformation matrices generated";

                if (changed.includes("representation"))
                    return "Cartesian representation calculated";

                if (changed.includes("group_theory"))
                    return "Representation reduced";

                if (changed.includes("verification"))
                    return "Scientific verification completed";

                return "Research state updated";
            }
        }

        return "Research event";
    }

    function timelineDetail(event) {
        const state = event?.payload?.state || {};
        const changed = event?.payload?.changed || [];

        if (changed.includes("operations")) {
            const operations = Array.isArray(state.operations)
                ? state.operations.length
                : 0;
            return `${operations} symmetry operations persisted.`;
        }

        if (changed.includes("matrices"))
            return "Cartesian transformation matrices persisted.";

        if (changed.includes("representation"))
            return "Representation matrices and characters persisted.";

        if (changed.includes("group_theory")) {
            return state?.group_theory?.reduction?.summary ||
                "Group-theory reduction persisted.";
        }

        if (changed.includes("verification")) {
            return state?.verification?.status === "PASS"
                ? "All scientific verification checks passed."
                : "Verification result persisted.";
        }

        return "";
    }

    function renderTimeline(events) {
        const root = $("timeline");

        $("event-count").textContent =
            `${events.length} event${events.length === 1 ? "" : "s"}`;

        if (!events.length) {
            root.innerHTML = '<div class="empty">No replay events.</div>';
            return;
        }

        root.innerHTML = events.map(event => `
            <div class="timeline-item">
                <div class="timeline-version">
                    Version ${esc(event.version ?? "—")}
                </div>
                <div class="timeline-title">
                    ${esc(timelineTitle(event))}
                </div>
                <div class="timeline-detail">
                    ${esc(timelineDetail(event))}
                </div>
            </div>
        `).join("");
    }

    async function loadReplay() {
        if (!sessionId) {
            $("replay-subtitle").textContent =
                "No research session was supplied.";
            return;
        }

        const response = await fetch(
            `/api/sessions/${encodeURIComponent(sessionId)}/replay?_=${Date.now()}`,
            {
                credentials: "same-origin",
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error("Unable to load research replay.");
        }

        const payload = await response.json();
        const state = stateFromPayload(payload);
        const events = Array.isArray(payload?.events)
            ? payload.events
            : [];

        const molecule =
            state?.molecule ||
            state?.molecule_data?.formula ||
            state?.molecule_data?.id ||
            "Research session";

        const pointGroup =
            state?.point_group ||
            state?.molecule_data?.point_group ||
            "—";

        const operations =
            Array.isArray(state?.operations)
                ? state.operations
                : [];

        $("replay-title").textContent =
            `${molecule} · Research Replay`;

        $("replay-subtitle").textContent =
            `Persisted session ${sessionId}`;

        $("molecule-value").textContent = molecule;
        $("point-group-value").textContent = pointGroup;
        $("operation-count-value").textContent = operations.length;

        renderOperations(operations);
        renderCharacters(state);
        renderReduction(state);
        renderVerification(state);
        renderTimeline(events);
    }

    $("refresh-replay")?.addEventListener("click", () => {
        loadReplay().catch(error => {
            console.error(error);
            $("replay-subtitle").textContent =
                "Unable to load the research replay.";
        });
    });

    loadReplay().catch(error => {
        console.error(error);
        $("replay-subtitle").textContent =
            "Unable to load the research replay.";
    });
})();

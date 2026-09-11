/* Dynamic Symmetry Analysis UI.
 * Scientific values come only from the active backend session.
 */
(function () {
    "use strict";

    const Analysis = {
        root: null,
        initialized: false,

        init() {
            if (this.initialized) return;
            this.root = document.querySelector(".quadrant-analysis");
            if (!this.root) return;

            this.initialized = true;

            document.addEventListener("voicelab:analysis-data", event => {
                this.update(event.detail || {});
            });

            this.reset();
        },

        reset() {
            this.setText("#point-group", "—");
            this.setText("#operation-count", "—");
            this.setText("#analysis-summary", "Waiting for symmetry analysis…");
            this.setText("#reduction-result", "Waiting for representation reduction…");
            this.setText("#symmetry-verification", "Waiting for geometric verification…");
            this.resetVibrationalAnalysis();

            const row = this.root.querySelector("#character-row");
            if (row) {
                row.innerHTML =
                    '<span class="character-empty">Waiting for character data…</span>';
            }

            this.setStatus("WAITING FOR DATA", false);
        },

        update(data) {
            const pointGroup = data.pointGroup ?? data.point_group ?? "—";
            const operations = Array.isArray(data.operations)
                ? data.operations
                : data.operationCount ?? data.operation_count;

            const characters =
                data.characters ||
                data.representation?.characters ||
                data.groupTheory?.reducible_characters ||
                {};

            const groupTheory =
                data.groupTheory ||
                data.group_theory ||
                {};

            const reduction =
                data.reduction ||
                groupTheory?.reduction ||
                groupTheory?.reduction_summary ||
                null;

            const verification =
                data.verification ||
                data.symmetryVerification ||
                data.symmetry_verification ||
                {};

            let summary = data.summary;
            if (!summary && data.molecule) {
                summary = String(data.molecule);
            }

            this.setText("#point-group", pointGroup);
            this.setText("#operation-count", this.operationValue(operations));
            this.setText(
                "#analysis-summary",
                summary || "Analysis data received."
            );
            this.setText("#reduction-result", this.formatCartesianRepresentation(reduction));
            this.renderVerification(data.operations, verification);
            this.renderCharacters(characters);
            this.renderVibrationalAnalysis(
                data.vibrational_analysis ||
                data.vibrationalAnalysis ||
                null
            );
            this.setStatus("LIVE ANALYSIS", true);
        },

        operationValue(value) {
            if (typeof value === "number") return String(value);
            if (Array.isArray(value)) return String(value.length);
            if (value && typeof value === "object") {
                if (typeof value.count === "number") return String(value.count);
                if (Array.isArray(value.elements)) return String(value.elements.length);
            }
            return value == null ? "—" : String(value);
        },

        formatCartesianRepresentation(reduction) {
            if (!reduction || typeof reduction !== "object") {
                return "Γ(x,y,z) = —";
            }

            const multiplicities = reduction.multiplicities || {};
            const prettyIrrep = {
                "A1'": "A₁′",
                "A2'": "A₂′",
                "E'": "E′",
                "A1''": "A₁″",
                "A2''": "A₂″",
                "E''": "E″"
            };

            const terms = [];

            for (const [irrep, count] of Object.entries(multiplicities)) {
                if (!count) continue;

                const pretty = prettyIrrep[irrep] || irrep;
                terms.push(
                    Number(count) === 1
                        ? pretty
                        : `${count}${pretty}`
                );
            }

            return `Γ(x,y,z) = ${terms.length ? terms.join(" + ") : "0"}`;
        },

        formatReduction(value) {
            /*
             * Reduction is scientific result data. Never stringify an
             * arbitrary backend/tool object into the visible UI because
             * that can leak internal error payloads.
             */
            if (value && typeof value === "object") {
                if (typeof value.summary === "string" && value.summary.trim()) {
                    return value.summary;
                }

                if (typeof value.reduction === "string" && value.reduction.trim()) {
                    return value.reduction;
                }

                if (typeof value.result === "string" && value.result.trim()) {
                    return value.result;
                }

                if (typeof value.expression === "string" && value.expression.trim()) {
                    return value.expression;
                }

                if (value.success === false || value.error || value.code) {
                    return "Representation reduction is not available yet.";
                }

                return "Waiting for representation reduction…";
            }

            return value == null || value === ""
                ? "Waiting for representation reduction…"
                : String(value);
        },

        resetVibrationalAnalysis() {
            const panel =
                this.root?.querySelector("#vibrational-analysis-panel");

            if (!panel) return;

            panel.hidden = true;

            this.setText(
                "#vibrational-reduction",
                "Waiting for vibrational analysis…"
            );

            this.setText("#ir-active-irreps", "—");
            this.setText("#raman-active-irreps", "—");

            const modes =
                this.root.querySelector("#vibrational-modes");

            if (modes) modes.innerHTML = "";
        },

        renderVibrationalAnalysis(vibrational) {
            const panel =
                this.root?.querySelector("#vibrational-analysis-panel");

            if (!panel) return;

            if (!vibrational || typeof vibrational !== "object") {
                panel.hidden = true;
                return;
            }

            const modes = Array.isArray(vibrational.vibrational_modes)
                ? vibrational.vibrational_modes
                : [];

            const activity =
                vibrational.activity &&
                typeof vibrational.activity === "object"
                    ? vibrational.activity
                    : {};

            const reduction =
                vibrational.reduction &&
                typeof vibrational.reduction === "object"
                    ? vibrational.reduction
                    : {};

            const reductionText =
                reduction.summary ||
                reduction.reduction ||
                reduction.expression ||
                (
                    typeof vibrational.vibrational_reduction === "string"
                        ? vibrational.vibrational_reduction
                        : "Vibrational representation available."
                );

            this.setText("#vibrational-reduction", reductionText);

            this.setText(
                "#ir-active-irreps",
                this.formatIrrepList(activity.ir_active_irreps)
            );

            this.setText(
                "#raman-active-irreps",
                this.formatIrrepList(
                    activity.raman_active_irreps
                )
            );

            const root =
                this.root.querySelector("#vibrational-modes");

            if (root) {
                root.innerHTML = modes.length
                    ? modes.map(mode => {
                        const irrep =
                            this.escapeHtml(
                                String(mode?.irrep ?? "—")
                            );

                        const multiplicity =
                            mode?.multiplicity ?? "—";

                        const degeneracy =
                            mode?.degeneracy ?? "—";

                        const coordinates =
                            mode?.normal_coordinates ?? "—";

                        const activityLabels = [];

                        if (mode?.ir_active === true) {
                            activityLabels.push("IR");
                        }

                        if (mode?.raman_active === true) {
                            activityLabels.push("Raman");
                        }

                        const active =
                            activityLabels.length
                                ? activityLabels.join(" + ")
                                : "Inactive";

                        return `
                            <div class="vibrational-mode">
                                <strong>${irrep}</strong>
                                <span>${this.escapeHtml(String(multiplicity))}×</span>
                                <span>deg ${this.escapeHtml(String(degeneracy))}</span>
                                <span>${this.escapeHtml(String(coordinates))} coord.</span>
                                <b>${this.escapeHtml(active)}</b>
                            </div>
                        `;
                    }).join("")
                    : '<span class="vibrational-empty">No normal-mode data supplied.</span>';
            }

            panel.hidden = false;
        },

        formatIrrepList(value) {
            if (!Array.isArray(value) || !value.length) {
                return "None";
            }

            return value
                .map(item => String(item))
                .join(" · ");
        },

        renderVerification(operations, verification = {}) {
            const root = this.root?.querySelector("#symmetry-verification");
            if (!root) return;

            const checks = verification?.checks;

            if (checks && typeof checks === "object") {
                const overall =
                    String(verification.status || "").toUpperCase();

                const header = "";

                const checkRows = Object.entries(checks).map(([name, status]) => {
                    const ok = String(status).toUpperCase() === "PASS";
                    const label = String(name)
                        .replaceAll("_", " ")
                        .replace(/\b\w/g, c => c.toUpperCase());

                    return `
                        <span class="symmetry-check ${ok ? "pass" : "fail"}">
                            <b>${this.escapeHtml(label)}</b>
                            <span>${ok ? "✓ PASS" : "✗ FAIL"}</span>
                        </span>
                    `;
                }).join("");

                root.innerHTML = header + checkRows;
                return;
            }

            if (!Array.isArray(operations) || !operations.length) {
                root.classList.add("verification-waiting");
                root.textContent = "Waiting for geometric verification…";
                return;
            }

            root.classList.remove("verification-waiting");
            root.innerHTML = operations.map(op => {
                const ok =
                    op &&
                    (
                        op.verified === true ||
                        op.verification?.status === "PASS"
                    );

                const symbol = op?.symbol || op?.id || "operation";

                return `
                    <span class="symmetry-check ${ok ? "pass" : "fail"}">
                        <b>${this.escapeHtml(String(symbol))}</b>
                        <span>${ok ? "✓ VERIFIED" : "✗ FAILED"}</span>
                    </span>
                `;
            }).join("");
        },

        escapeHtml(value) {
            return String(value)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        },

        renderCharacters(characters) {
            const row = this.root.querySelector("#character-row");
            if (!row) return;

            if (!characters || typeof characters !== "object") {
                row.innerHTML =
                    '<span class="character-empty">Waiting for character data…</span>';
                return;
            }

            const entries = Array.isArray(characters)
                ? characters.map((item, index) => {
                    if (Array.isArray(item)) {
                        return { label: item[0] ?? index, value: item[1] };
                    }
                    if (item && typeof item === "object") {
                        return {
                            label: item.label ?? item.operation ?? item.class ?? item.name ?? index,
                            value: item.value ?? item.character ?? item.chi
                        };
                    }
                    return { label: index, value: item };
                })
                : Object.entries(characters).map(([label, value]) => ({ label, value }));

            if (!entries.length) {
                row.innerHTML =
                    '<span class="character-empty">No character data supplied.</span>';
                return;
            }

            row.innerHTML = "";
            entries.forEach(entry => {
                const label = document.createElement("span");
                const value = document.createElement("b");
                label.textContent = String(entry.label);
                value.textContent = entry.value == null ? "—" : String(entry.value);
                row.append(label, value);
            });
        },

        setText(selector, value) {
            const element = this.root?.querySelector(selector);
            if (element) element.textContent = String(value);
        },

        setStatus(text, live) {
            const status = this.root?.querySelector(".analysis-status");
            if (!status) return;

            status.innerHTML = "<i></i> " + String(text);
            status.classList.toggle("is-waiting", !live);
        }
    };

    window.Analysis = Analysis;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => Analysis.init(), { once: true });
    } else {
        Analysis.init();
    }
})();

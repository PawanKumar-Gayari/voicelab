/* =========================================================
   Card 1 — Molecular Lab integration bridge
   Dynamic only: receives molecule data from the system.
   ========================================================= */

(function () {
    "use strict";

    const MolecularLab = {
        root: null,
        initialized: false,

        init() {
            if (this.initialized) return;

            this.root =
                document.getElementById("molecule-lab") ||
                document.getElementById("molecular-lab");

            if (!this.root) return;

            this.initialized = true;

            this.bindControls();
            this.bindViewerEvents();

            document.dispatchEvent(
                new CustomEvent("voicelab:molecular-lab-ready")
            );
        },

        bindControls() {
            this.root
                .querySelectorAll("[data-molecule-action]")
                .forEach(button => {
                    button.addEventListener("click", () => {
                        document.dispatchEvent(
                            new CustomEvent(
                                "voicelab:molecule-action",
                                {
                                    detail: {
                                        action:
                                            button.dataset.moleculeAction
                                    }
                                }
                            )
                        );
                    });
                });
        },

        bindViewerEvents() {
            document.addEventListener(
                "voicelab:molecule-status",
                event => {
                    const status =
                        this.root.querySelector(
                            "#molecule-viewer-status"
                        );

                    if (status) {
                        status.textContent =
                            event.detail?.message ||
                            "Waiting for molecular coordinates…";

                        status.dataset.state =
                            event.detail?.state ||
                            "active";
                    }
                }
            );

            document.addEventListener(
                "voicelab:molecule-meta",
                event => {
                    const meta =
                        this.root.querySelector(
                            "#molecule-viewer-meta"
                        );

                    if (meta) {
                        meta.textContent =
                            event.detail?.meta ||
                            "Waiting for molecule…";
                    }
                }
            );
        }
    };

    window.MolecularLab = MolecularLab;

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            () => MolecularLab.init(),
            { once: true }
        );
    } else {
        MolecularLab.init();
    }
})();

/* =========================================================
   VoiceLab — Dynamic Three.js Molecular Viewer
   No molecule list / no hardcoded molecule-selection logic.

   The system supplies molecule data through:
   document.dispatchEvent(new CustomEvent(
       "voicelab:molecule-data",
       { detail: { ... } }
   ));

   Supported detail shape:
   {
       id: "C2H4",
       name: "Ethylene",
       pointGroup: "D2h",
       atoms: [
           { element:"C", x:-0.67, y:0, z:0 },
           { element:"C", x: 0.67, y:0, z:0 }
       ],
       bonds: [
           { a:0, b:1, order:2 }
       ]
   }

   The viewer also accepts atoms as:
   ["C", x, y, z]

   If bonds are omitted, nearby atoms are connected automatically.
   ========================================================= */

(function () {
    "use strict";

    const COLORS = {
        H: 0xf1f5f9,
        C: 0x9ca3af,
        N: 0x4f8cff,
        O: 0xff5b62,
        F: 0x55d68c,
        B: 0xf28aa8,
        S: 0xf4c95d,
        P: 0xff9f43,
        Si: 0xf59e5b,
        Xe: 0x62d7ff
    };

    const RADII = {
        H: 0.25, C: 0.38, N: 0.36, O: 0.36, F: 0.34,
        B: 0.39, S: 0.42, P: 0.42, Si: 0.44, Xe: 0.50
    };

    const state = {
        root: null,
        scene: null,
        camera: null,
        renderer: null,
        moleculeGroup: null,
        animationId: 0,
        currentData: null,
        distance: 7,
        targetDistance: 7,
        dragging: false,
        pointerX: 0,
        pointerY: 0,
        rotationX: -0.18,
        rotationY: 0.55,
        showAtomLabels: false,
        showElementNames: false,
        labelGroup: null,
        highlightGroup: null
    };

    function dispatch(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }

    function status(message, type = "active") {
        dispatch("voicelab:molecule-status", {
            message,
            state: type
        });
    }

    function setMeta(data) {
        const label = data.name || data.label || data.id || "Molecule";
        const group = data.pointGroup || data.group || "—";
        const count = Array.isArray(data.atoms) ? data.atoms.length : 0;

        dispatch("voicelab:molecule-meta", {
            meta: `${label} · ${group} · ${count} atoms`
        });
    }

    function normalizeAtom(atom) {
        if (Array.isArray(atom)) {
            return {
                element: String(atom[0] || "X"),
                x: Number(atom[1]) || 0,
                y: Number(atom[2]) || 0,
                z: Number(atom[3]) || 0
            };
        }

        return {
            element: String(atom?.element || atom?.symbol || "X"),
            label: atom?.label || atom?.id || null,
            x: Number(atom?.x) || 0,
            y: Number(atom?.y) || 0,
            z: Number(atom?.z) || 0
        };
    }

    function clearGroup(group) {
        while (group.children.length) {
            const child = group.children.pop();

            child.traverse(object => {
                if (object.geometry) object.geometry.dispose();

                if (object.material) {
                    if (Array.isArray(object.material)) {
                        object.material.forEach(material => material.dispose());
                    } else {
                        object.material.dispose();
                    }
                }
            });
        }
    }

    function makeBond(start, end, order = 1) {
        const a = new THREE.Vector3(start.x, start.y, start.z);
        const b = new THREE.Vector3(end.x, end.y, end.z);

        const delta = new THREE.Vector3().subVectors(b, a);
        const length = delta.length();

        if (!length) return null;

        const direction = delta.clone().normalize();
        const midpoint = a.clone().add(b).multiplyScalar(0.5);

        const geometry = new THREE.CylinderGeometry(
            0.075,
            0.075,
            length,
            12
        );

        const material = new THREE.MeshStandardMaterial({
            color: 0x71819a,
            metalness: 0.30,
            roughness: 0.38
        });

        const bond = new THREE.Mesh(geometry, material);

        bond.position.copy(midpoint);

        bond.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            direction
        );

        return bond;
    }

    function makeTextSprite(text) {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = 256 * dpr;
        canvas.height = 96 * dpr;
        ctx.scale(dpr, dpr);
        ctx.font = "700 30px Inter, Arial, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "rgba(7,16,29,0.82)";
        ctx.roundRect?.(8, 8, 240, 80, 16);
        ctx.fill();
        if (!ctx.roundRect) { ctx.fillRect(8, 8, 240, 80); }
        ctx.fillStyle = "#f5f8ff";
        ctx.fillText(String(text), 128, 48);

        const texture = new THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;
        const material = new THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            depthTest: false
        });
        const sprite = new THREE.Sprite(material);
        sprite.scale.set(0.9, 0.34, 1);
        return sprite;
    }

    function rebuildLabels(displayAtoms) {
        if (!state.labelGroup) return;
        clearGroup(state.labelGroup);

        displayAtoms.forEach((atom, index) => {
            const atomLabel = atom.label || atom.id || `${atom.element}${index + 1}`;
            const parts = [];
            if (state.showAtomLabels) parts.push(atomLabel);
            if (state.showElementNames) parts.push(atom.element);
            if (!parts.length) return;

            const sprite = makeTextSprite(parts.join(" · "));
            sprite.position.set(atom.x, atom.y + (RADII[atom.element] || 0.34) + 0.18, atom.z);
            state.labelGroup.add(sprite);
        });
    }

    function setLabelMode(mode, enabled) {
        if (mode === "atom-labels") state.showAtomLabels = enabled;
        if (mode === "element-names") state.showElementNames = enabled;
        if (state.currentData?.atoms) {
            const center = state.currentData.atoms.reduce((sum, atom) => ({
                x: sum.x + atom.x, y: sum.y + atom.y, z: sum.z + atom.z
            }), {x: 0, y: 0, z: 0});
            const n = state.currentData.atoms.length || 1;
            center.x /= n; center.y /= n; center.z /= n;
            rebuildLabels(state.currentData.atoms.map(atom => ({
                ...atom, x: atom.x - center.x, y: atom.y - center.y, z: atom.z - center.z
            })));
        }
        dispatch("voicelab:molecule-label-state", {
            atomLabels: state.showAtomLabels,
            elementNames: state.showElementNames
        });
    }

    function buildBonds(atoms, explicitBonds) {
        const bonds = [];

        if (Array.isArray(explicitBonds) && explicitBonds.length) {
            explicitBonds.forEach(item => {
                const a = Number(item.a ?? item.from);
                const b = Number(item.b ?? item.to);

                if (
                    Number.isInteger(a) &&
                    Number.isInteger(b) &&
                    atoms[a] &&
                    atoms[b]
                ) {
                    bonds.push([a, b, Number(item.order) || 1]);
                }
            });

            return bonds;
        }

        /*
         * Generic fallback only.
         * The viewer does not know molecule identities.
         * It simply uses coordinates to find close atom pairs.
         */
        for (let i = 0; i < atoms.length; i++) {
            for (let j = i + 1; j < atoms.length; j++) {
                const a = atoms[i];
                const b = atoms[j];

                const dx = a.x - b.x;
                const dy = a.y - b.y;
                const dz = a.z - b.z;
                const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);

                if (distance > 0.45 && distance < 1.9) {
                    bonds.push([i, j, 1]);
                }
            }
        }

        return bonds;
    }

    function clearHighlights() {
        if (state.highlightGroup) clearGroup(state.highlightGroup);
    }

    function addAxisHighlight(axis, length = 2.5, label = "") {
        const vector = new THREE.Vector3(Number(axis?.[0]) || 0, Number(axis?.[1]) || 0, Number(axis?.[2]) || 0);
        if (vector.lengthSq() < 1e-12) return;
        vector.normalize();
        const start = vector.clone().multiplyScalar(-length);
        const end = vector.clone().multiplyScalar(length);
        const geometry = new THREE.BufferGeometry().setFromPoints([start, end]);
        const material = new THREE.LineBasicMaterial({color: 0x66a3ff, transparent: true, opacity: 0.95});
        const line = new THREE.Line(geometry, material);
        state.highlightGroup.add(line);
        if (label) {
            const sprite = makeTextSprite(label);
            sprite.scale.set(0.75, 0.28, 1);
            sprite.position.copy(vector.clone().multiplyScalar(length * 1.08));
            state.highlightGroup.add(sprite);
        }
    }

    function addPlaneHighlight(normal, size = 4.2, label = "σh") {
        const n = new THREE.Vector3(Number(normal?.[0]) || 0, Number(normal?.[1]) || 0, Number(normal?.[2]) || 0);
        if (n.lengthSq() < 1e-12) return;
        n.normalize();
        const plane = new THREE.Mesh(
            new THREE.PlaneGeometry(size, size),
            new THREE.MeshBasicMaterial({color: 0x4f7cff, transparent: true, opacity: 0.10, side: THREE.DoubleSide, depthWrite: false})
        );
        plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
        state.highlightGroup.add(plane);
        if (label) {
            const sprite = makeTextSprite(label);
            sprite.scale.set(0.75, 0.28, 1);
            sprite.position.set(0, 0, 0);
            state.highlightGroup.add(sprite);
        }
    }

    function showSymmetryHighlight(kind) {
        if (!state.highlightGroup || !state.currentData) return;
        clearHighlights();
        const operations = Array.isArray(state.currentData.operations) ? state.currentData.operations : [];
        if (kind === "c3") {
            const op = operations.find(x => String(x.id || "").startsWith("C3_"));
            addAxisHighlight(op?.axis || [0,0,1], 2.7, "C₃");
        } else if (kind === "c2") {
            operations.filter(x => String(x.class || "").includes("C2") || String(x.id || "").startsWith("C2p_"))
                .forEach((op, i) => addAxisHighlight(op.axis || [1,0,0], 2.45, i === 0 ? "3 C₂′" : ""));
        } else if (kind === "sigma-h") {
            const op = operations.find(x => String(x.id || "") === "sigma_h");
            addPlaneHighlight(op?.plane_normal || [0,0,1], 4.5, "σh");
        }
        dispatch("voicelab:molecule-highlight", {kind});
    }

    function loadMolecule(data) {
        if (!data || !Array.isArray(data.atoms) || !data.atoms.length) {
            status("Waiting for molecular coordinates…", "waiting");
            setMeta({
                name: "Waiting for molecule",
                pointGroup: "—",
                atoms: []
            });
            return;
        }

        const atoms = data.atoms.map(normalizeAtom);
        const bonds = buildBonds(atoms, data.bonds);

        clearGroup(state.moleculeGroup);

        // Center every registry-supplied geometry around its centroid so the
        // viewer works for arbitrary molecules without molecule-specific code.
        const center = atoms.reduce(
            (sum, atom) => {
                sum.x += atom.x;
                sum.y += atom.y;
                sum.z += atom.z;
                return sum;
            },
            { x: 0, y: 0, z: 0 }
        );

        center.x /= atoms.length;
        center.y /= atoms.length;
        center.z /= atoms.length;

        const displayAtoms = atoms.map(atom => ({
            ...atom,
            x: atom.x - center.x,
            y: atom.y - center.y,
            z: atom.z - center.z
        }));

        const atomGroup = new THREE.Group();
        const bondGroup = new THREE.Group();

        displayAtoms.forEach(atom => {
            const element = atom.element;
            const radius = RADII[element] || 0.34;

            const geometry = new THREE.SphereGeometry(
                radius,
                28,
                20
            );

            const material = new THREE.MeshStandardMaterial({
                color: COLORS[element] || 0xd9e2ef,
                metalness: 0.18,
                roughness: 0.30
            });

            const mesh = new THREE.Mesh(geometry, material);

            mesh.position.set(
                atom.x,
                atom.y,
                atom.z
            );

            mesh.userData.element = element;

            atomGroup.add(mesh);
        });

        bonds.forEach(([a, b, order]) => {
            const bond = makeBond(displayAtoms[a], displayAtoms[b], order);
            if (bond) bondGroup.add(bond);
        });

        state.moleculeGroup.add(bondGroup);
        state.moleculeGroup.add(atomGroup);
        state.labelGroup = new THREE.Group();
        state.moleculeGroup.add(state.labelGroup);
        state.highlightGroup = new THREE.Group();
        state.moleculeGroup.add(state.highlightGroup);
        rebuildLabels(displayAtoms);

        const previousData = state.currentData;
        const previousRotationX = state.rotationX;
        const previousRotationY = state.rotationY;
        const previousTargetDistance = state.targetDistance;
        const previousDistance = state.distance;

        const previousId = previousData?.id || previousData?.moleculeId || previousData?.name || previousData?.label;
        const nextId = data?.id || data?.moleculeId || data?.name || data?.label;
        const sameMolecule = Boolean(previousId && nextId && previousId === nextId);

        state.currentData = {
            ...data,
            atoms,
            operations: Array.isArray(data.operations) ? data.operations : []
        };

        // Preserve the user's viewer state when the same molecule is
        // re-emitted after a voice/tool action. Only a genuinely new
        // molecule gets the default orientation and automatic camera fit.
        if (sameMolecule) {
            state.rotationX = previousRotationX;
            state.rotationY = previousRotationY;
            state.targetDistance = previousTargetDistance;
            state.distance = previousDistance;
        } else {
            state.rotationX = -0.18;
            state.rotationY = 0.55;

            // Automatically fit the camera to the supplied geometry.
            let maxRadius = 1;
            displayAtoms.forEach(atom => {
                maxRadius = Math.max(
                    maxRadius,
                    Math.sqrt(atom.x ** 2 + atom.y ** 2 + atom.z ** 2) + (RADII[atom.element] || 0.34)
                );
            });

            state.targetDistance = Math.max(4.5, Math.min(18, maxRadius * 3.2));
            state.distance = state.targetDistance;
        }

        setMeta(data);
        status(
            `${data.name || data.label || data.id || "Molecule"} loaded`,
            "active"
        );

        dispatch("voicelab:molecule-rendered", {
            molecule: data
        });
    }

    function resize() {
        if (!state.root || !state.renderer || !state.camera) return;

        const width = Math.max(1, state.root.clientWidth);
        const height = Math.max(1, state.root.clientHeight);

        state.camera.aspect = width / height;
        state.camera.updateProjectionMatrix();

        state.renderer.setSize(width, height, false);
        state.renderer.setPixelRatio(
            Math.min(window.devicePixelRatio || 1, 1.8)
        );
    }

    function render() {
        state.distance +=
            (state.targetDistance - state.distance) * 0.10;

        state.camera.position.set(
            0,
            0,
            state.distance
        );

        state.camera.lookAt(0, 0, 0);

        state.moleculeGroup.rotation.x = state.rotationX;
        state.moleculeGroup.rotation.y = state.rotationY;

        state.renderer.render(
            state.scene,
            state.camera
        );

        state.animationId = requestAnimationFrame(render);
    }

    function action(actionName) {
        switch (actionName) {
            case "rotate-left":
                state.rotationY -= Math.PI / 6;
                break;

            case "rotate-right":
                state.rotationY += Math.PI / 6;
                break;

            case "zoom-in":
                state.targetDistance = Math.max(
                    3,
                    state.targetDistance - 0.7
                );
                break;

            case "zoom-out":
                state.targetDistance = Math.min(
                    18,
                    state.targetDistance + 0.7
                );
                break;

            case "show-atom-labels":
                setLabelMode("atom-labels", true);
                break;

            case "hide-atom-labels":
                setLabelMode("atom-labels", false);
                break;

            case "show-element-names":
                setLabelMode("element-names", true);
                break;

            case "hide-element-names":
                setLabelMode("element-names", false);
                break;

            case "show-c3-axis":
                showSymmetryHighlight("c3");
                break;

            case "show-c2-axes":
                showSymmetryHighlight("c2");
                break;

            case "show-sigma-h":
                showSymmetryHighlight("sigma-h");
                break;

            case "clear-highlights":
                clearHighlights();
                break;

            case "reset":
                state.rotationX = -0.18;
                state.rotationY = 0.55;
                clearHighlights();

                if (state.currentData?.atoms) {
                    state.targetDistance = Math.max(
                        4.5,
                        4.8 +
                        Math.sqrt(state.currentData.atoms.length) * 0.65
                    );
                }
                break;
        }
        const highlight = actionName === "show-c3-axis" ? "c3" : actionName === "show-c2-axes" ? "c2" : actionName === "show-sigma-h" ? "sigma-h" : actionName === "clear-highlights" || actionName === "reset" ? "none" : undefined;
        dispatch("voicelab:molecule-viewer-action-result", {
            action: actionName,
            success: true,
            atomLabels: state.showAtomLabels,
            elementNames: state.showElementNames,
            highlight
        });
    }

    function setupInteraction() {
        const el = state.root;

        el.addEventListener("pointerdown", event => {
            state.dragging = true;
            state.pointerX = event.clientX;
            state.pointerY = event.clientY;
            el.setPointerCapture?.(event.pointerId);
        });

        el.addEventListener("pointermove", event => {
            if (!state.dragging) return;

            const dx = event.clientX - state.pointerX;
            const dy = event.clientY - state.pointerY;

            state.pointerX = event.clientX;
            state.pointerY = event.clientY;

            state.rotationY += dx * 0.009;
            state.rotationX += dy * 0.009;

            state.rotationX = Math.max(
                -1.35,
                Math.min(1.35, state.rotationX)
            );
        });

        el.addEventListener("pointerup", event => {
            state.dragging = false;
            el.releasePointerCapture?.(event.pointerId);
        });

        el.addEventListener("pointercancel", () => {
            state.dragging = false;
        });

        el.addEventListener(
            "wheel",
            event => {
                event.preventDefault();

                state.targetDistance +=
                    event.deltaY * 0.004;

                state.targetDistance = Math.max(
                    3,
                    Math.min(18, state.targetDistance)
                );
            },
            { passive: false }
        );
    }

    function init() {
        state.root =
            document.getElementById("molecule-viewer");

        if (!state.root) return;

        if (!window.THREE) {
            status(
                "Three.js could not be loaded.",
                "error"
            );
            setMeta({
                name: "Three.js unavailable",
                pointGroup: "—",
                atoms: []
            });
            return;
        }

        state.scene = new THREE.Scene();
        state.scene.background =
            new THREE.Color(0x07101d);

        state.camera =
            new THREE.PerspectiveCamera(42, 1, 0.1, 100);

        state.camera.position.z =
            state.distance;

        state.renderer =
            new THREE.WebGLRenderer({
                antialias: true,
                alpha: false
            });

        state.renderer.setPixelRatio(
            Math.min(window.devicePixelRatio || 1, 1.8)
        );

        state.renderer.setSize(1, 1, false);
        state.renderer.setClearColor(
            0x07101d,
            1
        );

        state.root.innerHTML = "";
        state.root.appendChild(
            state.renderer.domElement
        );

        state.scene.add(
            new THREE.AmbientLight(
                0xffffff,
                1.45
            )
        );

        const key =
            new THREE.DirectionalLight(
                0xffffff,
                2.0
            );

        key.position.set(4, 6, 8);
        state.scene.add(key);

        const rim =
            new THREE.DirectionalLight(
                0x4f7cff,
                1.25
            );

        rim.position.set(-6, 2, -4);
        state.scene.add(rim);

        const fill =
            new THREE.PointLight(
                0x2dd4bf,
                1.0,
                14
            );

        fill.position.set(0, -3, 5);
        state.scene.add(fill);

        state.moleculeGroup =
            new THREE.Group();

        state.scene.add(
            state.moleculeGroup
        );

        setupInteraction();
        resize();

        window.addEventListener(
            "resize",
            resize
        );

        /*
         * Dynamic system input.
         * No molecule names are checked here.
         */
        document.addEventListener(
            "voicelab:molecule-data",
            event => loadMolecule(event.detail)
        );

        document.addEventListener(
            "voicelab:molecule-action",
            event => action(
                event.detail?.action
            )
        );

        status(
            "Waiting for molecular coordinates…",
            "waiting"
        );

        setMeta({
            name: "Waiting for molecule",
            pointGroup: "—",
            atoms: []
        });

        render();

        dispatch(
            "voicelab:molecule-viewer-ready",
            {}
        );
    }

    window.MoleculeViewer = {
        load: loadMolecule,
        action
    };

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            init,
            { once: true }
        );
    } else {
        init();
    }
})();

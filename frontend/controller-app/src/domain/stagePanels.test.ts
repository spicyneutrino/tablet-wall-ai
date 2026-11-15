import { expect, it } from "vitest";
import { fit as fitMeasured, measureWell } from "./stagePanels";
import type { FitResult } from "./stagePanels";

it("operator_stage_fit.test.js", () => {
    class LabelNode {
        attrs = new Map<string, string>();
        style: Record<string, string> = {};
        dataset: Record<string, string> = {};
        textContent = "";
        getScreenCTM() { return { a: 0, b: 0 }; }
        setAttribute(name: string, value: string | number) { this.attrs.set(name, String(value)); }
        getAttribute(name: string) { return this.attrs.get(name) ?? null; }
    }
    const win = { getComputedStyle: (node: { computed: Record<string, string> }) => node.computed };
    const doc = { defaultView: win, body: { dataset: {} as Record<string, string> } };
    const well = { clientWidth: 1000, clientHeight: 600, getClientRects: (): number[] => [1],
        computed: { paddingLeft: "16px", paddingRight: "16px", paddingTop: "8px", paddingBottom: "8px" } };
    const parent = { computed: { rowGap: "8px" } };
    const tally = { getBoundingClientRect: () => ({ height: 28 }) };
    const field = { parentElement: parent, style: {} as { inlineSize: string },
        computed: { borderLeftWidth: "1px", borderRightWidth: "1px", borderTopWidth: "1px", borderBottomWidth: "1px" } };
    let dragging = false, rotation = 0;
    const label = new LabelNode();
    label.dataset = { width: "667", height: "354", x: "0", y: "0", label: "Screen 1" };
    const svg = { classList: { contains: () => dragging }, ownerDocument: doc,
        viewBox: { baseVal: { width: 720, height: 370 } }, style: {} as { inlineSize: string }, closest: () => field,
        querySelectorAll: (selector: string) => selector === ".operator-slot-label" ? [label] : [] };
    label.getScreenCTM = () => {
        const scale = parseFloat(svg.style.inlineSize) / 720 * 0.35;
        return { a: scale * Math.cos(rotation), b: scale * Math.sin(rotation) };
    };
    const fit = (): FitResult | null => {
        if (!svg.viewBox.baseVal.width) return null;
        const available = measureWell(svg as unknown as SVGSVGElement,
            { well: well as unknown as HTMLElement, field: field as unknown as HTMLElement, tally: tally as unknown as HTMLElement });
        return available ? fitMeasured(svg as unknown as SVGSVGElement, available, { field: field as unknown as HTMLElement }) : null;
    };
    let result = fit();
    expect(result!.width).toBe(966);
    expect(parseFloat(field.style.inlineSize)).toBe(968);
    expect(result!.width / result!.height).toBe(720 / 370);
    const dragSize = { ...svg.style };
    dragging = true;
    expect(fit()).toBe(null);
    expect(svg.style).toEqual(dragSize);
    dragging = false;
    expect(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b)).toBe(16);
    well.clientHeight = 300;
    result = fit();
    expect(result!.height).toBe(246);
    expect(result!.width).toBe(246 * 720 / 370);
    const stable = { ...result! };
    for (const mode of ["content", "arrange", "test"]) {
        doc.body.dataset.mode = mode;
        expect(fit()).toEqual(stable);
    }
    rotation = Math.PI / 3;
    fit();
    expect(Math.abs(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b) - 16) < 1e-10).toBeTruthy();
    well.clientWidth = 170;
    label.dataset.label = "Tablet 2";
    fit();
    expect(label.textContent).toBe("2");
    well.clientWidth = 1000;
    const measured = fitMeasured(svg as unknown as SVGSVGElement, { width: 640, height: 300 }, { field: field as unknown as HTMLElement });
    expect(measured!.height).toBe(300);
    expect(measured!.width).toBe(300 * (720 / 370));
    well.getClientRects = () => [];
    expect(fit()).toBe(null);
});

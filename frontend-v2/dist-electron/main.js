import { createRequire as e } from "node:module";
import { BrowserWindow as t, app as n, ipcMain as r } from "electron";
import { fileURLToPath as i } from "node:url";
import a from "node:path";
import { exec as o } from "node:child_process";
//#region electron/main.ts
e(import.meta.url);
var s = a.dirname(i(import.meta.url));
process.env.APP_ROOT = a.join(s, "..");
var c = process.env.VITE_DEV_SERVER_URL, l = a.join(process.env.APP_ROOT, "dist-electron"), u = a.join(process.env.APP_ROOT, "dist");
process.env.VITE_PUBLIC = c ? a.join(process.env.APP_ROOT, "public") : u;
var d, f = [];
function p() {
	d = new t({
		icon: a.join(process.env.VITE_PUBLIC, "electron-vite.svg"),
		width: 1200,
		height: 800,
		backgroundColor: "#0E1C31",
		webPreferences: {
			preload: a.join(s, "preload.js"),
			contextIsolation: !0,
			nodeIntegration: !1
		}
	}), d.webContents.on("did-finish-load", () => {
		d?.webContents.send("main-process-message", (/* @__PURE__ */ new Date()).toLocaleString());
	}), c ? d.loadURL(c) : d.loadFile(a.join(u, "index.html"));
}
n.on("window-all-closed", () => {
	process.platform !== "darwin" && (n.quit(), d = null);
}), n.on("activate", () => {
	t.getAllWindows().length === 0 && p();
}), n.whenReady().then(() => {
	r.handle("set_safe_mode", async (e, t) => (d?.webContents.send("runtime-event", {
		type: "safe_mode.changed",
		mode: t
	}), `safe mode set: ${t}`)), r.handle("start_screen_preview", async (e, t) => new Promise((e, r) => {
		let i = Date.now(), s = a.join(n.getPath("temp"), `owlynn-preview-${t}-${i}.jpg`);
		process.platform === "darwin" ? o(`screencapture -x -t jpg "${s}"`, (n) => {
			n ? r(/* @__PURE__ */ Error(`screencapture failed: ${n.message}`)) : (d?.webContents.send("runtime-event", {
				type: "screen_assist.state",
				mode: "preview",
				source: t,
				preview_path: s
			}), e(`screen preview started: ${t} (${s})`));
		}) : r(/* @__PURE__ */ Error("Screen capture only implemented for macOS in this version"));
	})), r.handle("stop_screen_preview", async () => (d?.webContents.send("runtime-event", {
		type: "screen_assist.state",
		mode: "off",
		source: "screen",
		preview_path: null
	}), "screen preview stopped")), r.handle("create_action_proposal", async (e, t) => {
		let n = {
			id: `proposal-${Date.now()}`,
			summary: t,
			source: "screen_assist",
			created_at: Date.now(),
			status: "pending"
		};
		return f.push(n), d?.webContents.send("runtime-event", {
			type: "action.proposal",
			proposal: n
		}), n;
	}), r.handle("approve_action_proposal", async (e, t) => {
		let n = f.find((e) => e.id === t);
		if (n) return n.status = "approved", d?.webContents.send("runtime-event", {
			type: "action.proposal.result",
			id: t,
			status: "approved"
		}), `proposal approved: ${t}`;
		throw Error(`proposal not found: ${t}`);
	}), r.handle("reject_action_proposal", async (e, t) => {
		let n = f.find((e) => e.id === t);
		if (n) return n.status = "rejected", d?.webContents.send("runtime-event", {
			type: "action.proposal.result",
			id: t,
			status: "rejected"
		}), `proposal rejected: ${t}`;
		throw Error(`proposal not found: ${t}`);
	}), r.handle("set_window_size", async (e, t, n) => {
		if (d) return d.setContentSize(Math.round(t), Math.round(n)), `window resized to ${t}x${n}`;
		throw Error("main window not found");
	}), p();
});
//#endregion
export { l as MAIN_DIST, u as RENDERER_DIST, c as VITE_DEV_SERVER_URL };

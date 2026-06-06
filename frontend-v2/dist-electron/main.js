import { createRequire } from "node:module";
import { BrowserWindow, app, ipcMain } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { exec } from "node:child_process";
//#region electron/main.ts
createRequire(import.meta.url);
var __dirname = path.dirname(fileURLToPath(import.meta.url));
process.env.APP_ROOT = path.join(__dirname, "..");
var VITE_DEV_SERVER_URL = process.env["VITE_DEV_SERVER_URL"];
var MAIN_DIST = path.join(process.env.APP_ROOT, "dist-electron");
var RENDERER_DIST = path.join(process.env.APP_ROOT, "dist");
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, "public") : RENDERER_DIST;
var win;
var proposals = [];
function createWindow() {
	win = new BrowserWindow({
		icon: path.join(process.env.VITE_PUBLIC, "electron-vite.svg"),
		width: 1200,
		height: 800,
		backgroundColor: "#0E1C31",
		webPreferences: {
			preload: path.join(__dirname, "preload.js"),
			contextIsolation: true,
			nodeIntegration: false
		}
	});
	win.webContents.on("did-finish-load", () => {
		win?.webContents.send("main-process-message", (/* @__PURE__ */ new Date()).toLocaleString());
	});
	if (VITE_DEV_SERVER_URL) win.loadURL(VITE_DEV_SERVER_URL);
	else win.loadFile(path.join(RENDERER_DIST, "index.html"));
}
app.on("window-all-closed", () => {
	if (process.platform !== "darwin") {
		app.quit();
		win = null;
	}
});
app.on("activate", () => {
	if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
app.whenReady().then(() => {
	ipcMain.handle("set_safe_mode", async (event, mode) => {
		win?.webContents.send("runtime-event", {
			type: "safe_mode.changed",
			mode
		});
		return `safe mode set: ${mode}`;
	});
	ipcMain.handle("start_screen_preview", async (event, source) => {
		return new Promise((resolve, reject) => {
			const millis = Date.now();
			const previewPath = path.join(app.getPath("temp"), `owlynn-preview-${source}-${millis}.jpg`);
			if (process.platform === "darwin") exec(`screencapture -x -t jpg "${previewPath}"`, (error) => {
				if (error) reject(/* @__PURE__ */ new Error(`screencapture failed: ${error.message}`));
				else {
					win?.webContents.send("runtime-event", {
						type: "screen_assist.state",
						mode: "preview",
						source,
						preview_path: previewPath
					});
					resolve(`screen preview started: ${source} (${previewPath})`);
				}
			});
			else reject(/* @__PURE__ */ new Error("Screen capture only implemented for macOS in this version"));
		});
	});
	ipcMain.handle("stop_screen_preview", async () => {
		win?.webContents.send("runtime-event", {
			type: "screen_assist.state",
			mode: "off",
			source: "screen",
			preview_path: null
		});
		return "screen preview stopped";
	});
	ipcMain.handle("create_action_proposal", async (event, summary) => {
		const proposal = {
			id: `proposal-${Date.now()}`,
			summary,
			source: "screen_assist",
			created_at: Date.now(),
			status: "pending"
		};
		proposals.push(proposal);
		win?.webContents.send("runtime-event", {
			type: "action.proposal",
			proposal
		});
		return proposal;
	});
	ipcMain.handle("approve_action_proposal", async (event, id) => {
		const proposal = proposals.find((p) => p.id === id);
		if (proposal) {
			proposal.status = "approved";
			win?.webContents.send("runtime-event", {
				type: "action.proposal.result",
				id,
				status: "approved"
			});
			return `proposal approved: ${id}`;
		}
		throw new Error(`proposal not found: ${id}`);
	});
	ipcMain.handle("reject_action_proposal", async (event, id) => {
		const proposal = proposals.find((p) => p.id === id);
		if (proposal) {
			proposal.status = "rejected";
			win?.webContents.send("runtime-event", {
				type: "action.proposal.result",
				id,
				status: "rejected"
			});
			return `proposal rejected: ${id}`;
		}
		throw new Error(`proposal not found: ${id}`);
	});
	ipcMain.handle("set_window_size", async (event, width, height) => {
		if (win) {
			win.setContentSize(Math.round(width), Math.round(height));
			return `window resized to ${width}x${height}`;
		}
		throw new Error("main window not found");
	});
	createWindow();
});
//#endregion
export { MAIN_DIST, RENDERER_DIST, VITE_DEV_SERVER_URL };

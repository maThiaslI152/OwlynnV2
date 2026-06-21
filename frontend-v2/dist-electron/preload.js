import { contextBridge as e, ipcRenderer as t } from "electron";
e.exposeInMainWorld("ipcRenderer", {
	on(...e) {
		let [n, r] = e;
		return t.on(n, (e, ...t) => r(e, ...t));
	},
	off(...e) {
		let [n, ...r] = e;
		return t.off(n, ...r);
	},
	send(...e) {
		let [n, ...r] = e;
		return t.send(n, ...r);
	},
	invoke(...e) {
		let [n, ...r] = e;
		return t.invoke(n, ...r);
	}
}), e.exposeInMainWorld("electronAPI", {
	invoke: (e, n) => t.invoke(e, n),
	on: (e, n) => {
		let r = (e, ...t) => n(...t);
		return t.on(e, r), () => t.off(e, r);
	}
});
//#endregion
export {};

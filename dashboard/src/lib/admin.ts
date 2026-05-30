// Admin "Connections hub" API client.

export interface SourceField {
	key: string;
	label: string;
	secret: boolean;
	required: boolean;
	env: string;
	placeholder: string;
	saved: boolean;
	env_fallback: boolean;
	value: string;
}

export interface SourceStatus {
	name: string;
	label: string;
	kind: string;
	notes: string;
	needs_credentials: boolean;
	fields: SourceField[];
	configured: boolean;
	active: boolean;
}

export interface AdminSources {
	active: string;
	sources: SourceStatus[];
}

export interface TestResult {
	name: string;
	ok: boolean;
	message: string;
	latency_ms: number;
}

const BASE = '/api/admin';

export async function getSources(): Promise<AdminSources> {
	const r = await fetch(`${BASE}/sources`);
	if (!r.ok) throw new Error(`API ${r.status}`);
	return r.json();
}

export async function saveCredentials(name: string, credentials: Record<string, string>): Promise<SourceStatus> {
	const r = await fetch(`${BASE}/sources/${name}`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ credentials })
	});
	if (!r.ok) throw new Error(`Save failed (${r.status})`);
	return r.json();
}

export async function testConnection(name: string, credentials: Record<string, string>): Promise<TestResult> {
	const r = await fetch(`${BASE}/sources/${name}/test`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ credentials })
	});
	if (!r.ok) throw new Error(`Test failed (${r.status})`);
	return r.json();
}

export async function setActive(name: string): Promise<void> {
	const r = await fetch(`${BASE}/active/${name}`, { method: 'PUT' });
	if (!r.ok) throw new Error(`Activate failed (${r.status})`);
}

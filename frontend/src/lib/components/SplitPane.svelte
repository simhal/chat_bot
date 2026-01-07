<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		upperContent: any;
		lowerContent: any;
		initialRatio?: number;
		minUpperPx?: number;
		minLowerPx?: number;
		storageKey?: string;
	}

	let {
		upperContent,
		lowerContent,
		initialRatio = 0.7,
		minUpperPx = 200,
		minLowerPx = 150,
		storageKey = 'splitPaneRatio'
	}: Props = $props();

	let splitRatio = $state(initialRatio);
	let isDragging = $state(false);
	let containerRef: HTMLDivElement;

	// Load saved ratio from localStorage
	onMount(() => {
		const saved = localStorage.getItem(storageKey);
		if (saved) {
			const parsed = parseFloat(saved);
			if (!isNaN(parsed) && parsed >= 0.1 && parsed <= 0.9) {
				splitRatio = parsed;
			}
		}
	});

	function startDrag(e: MouseEvent) {
		e.preventDefault();
		isDragging = true;
		document.addEventListener('mousemove', onDrag);
		document.addEventListener('mouseup', stopDrag);
		document.body.style.cursor = 'row-resize';
		document.body.style.userSelect = 'none';
	}

	function onDrag(e: MouseEvent) {
		if (!isDragging || !containerRef) return;

		const rect = containerRef.getBoundingClientRect();
		const containerHeight = rect.height;
		const mouseY = e.clientY - rect.top;

		// Calculate new ratio
		let newRatio = mouseY / containerHeight;

		// Apply min constraints
		const minUpperRatio = minUpperPx / containerHeight;
		const minLowerRatio = minLowerPx / containerHeight;
		const maxRatio = 1 - minLowerRatio;

		newRatio = Math.max(minUpperRatio, Math.min(maxRatio, newRatio));

		splitRatio = newRatio;
	}

	function stopDrag() {
		isDragging = false;
		document.removeEventListener('mousemove', onDrag);
		document.removeEventListener('mouseup', stopDrag);
		document.body.style.cursor = '';
		document.body.style.userSelect = '';

		// Save to localStorage
		localStorage.setItem(storageKey, splitRatio.toString());
	}

	// Touch support
	function startTouchDrag(e: TouchEvent) {
		e.preventDefault();
		isDragging = true;
		document.addEventListener('touchmove', onTouchDrag, { passive: false });
		document.addEventListener('touchend', stopTouchDrag);
	}

	function onTouchDrag(e: TouchEvent) {
		if (!isDragging || !containerRef) return;
		e.preventDefault();

		const touch = e.touches[0];
		const rect = containerRef.getBoundingClientRect();
		const containerHeight = rect.height;
		const touchY = touch.clientY - rect.top;

		let newRatio = touchY / containerHeight;

		const minUpperRatio = minUpperPx / containerHeight;
		const minLowerRatio = minLowerPx / containerHeight;
		const maxRatio = 1 - minLowerRatio;

		newRatio = Math.max(minUpperRatio, Math.min(maxRatio, newRatio));

		splitRatio = newRatio;
	}

	function stopTouchDrag() {
		isDragging = false;
		document.removeEventListener('touchmove', onTouchDrag);
		document.removeEventListener('touchend', stopTouchDrag);
		localStorage.setItem(storageKey, splitRatio.toString());
	}
</script>

<div class="split-container" bind:this={containerRef}>
	<div class="upper-pane" style="height: {splitRatio * 100}%">
		{@render upperContent()}
	</div>

	<div
		class="divider"
		class:dragging={isDragging}
		onmousedown={startDrag}
		ontouchstart={startTouchDrag}
		role="separator"
		aria-orientation="horizontal"
		aria-valuenow={Math.round(splitRatio * 100)}
		tabindex="0"
	>
		<div class="divider-handle"></div>
	</div>

	<div class="lower-pane" style="height: {(1 - splitRatio) * 100}%">
		{@render lowerContent()}
	</div>
</div>

<style>
	.split-container {
		display: flex;
		flex-direction: column;
		height: calc(100vh - 60px); /* Account for header */
		width: 100%;
		overflow: hidden;
	}

	.upper-pane {
		overflow: auto;
		min-height: 0;
	}

	.lower-pane {
		overflow: hidden;
		display: flex;
		flex-direction: column;
		min-height: 0;
	}

	.divider {
		flex-shrink: 0;
		height: 8px;
		background: linear-gradient(to bottom, #e5e7eb, #d1d5db, #e5e7eb);
		cursor: row-resize;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.15s ease;
		border-top: 1px solid #d1d5db;
		border-bottom: 1px solid #d1d5db;
	}

	.divider:hover,
	.divider.dragging {
		background: linear-gradient(to bottom, #d1d5db, #9ca3af, #d1d5db);
	}

	.divider-handle {
		width: 40px;
		height: 4px;
		background: #9ca3af;
		border-radius: 2px;
		transition: background 0.15s ease, width 0.15s ease;
	}

	.divider:hover .divider-handle,
	.divider.dragging .divider-handle {
		background: #6b7280;
		width: 60px;
	}

	/* Prevent text selection during drag */
	.split-container :global(*) {
		user-select: none;
	}

	.split-container:not(:has(.divider.dragging)) :global(*) {
		user-select: auto;
	}
</style>

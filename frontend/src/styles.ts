// Panel styles. Colors come from HA theme variables (with fallbacks) so light,
// dark and custom themes all apply.

import { css } from "lit";

export const panelStyles = css`
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
    -webkit-font-smoothing: antialiased;
  }

  .toolbar {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 8px;
    box-sizing: border-box;
    height: var(--header-height, 56px);
    padding: 0 12px 0 16px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    border-bottom: var(--app-header-border-bottom, none);
  }

  .title {
    flex: 1;
    min-width: 0;
    font-size: 20px;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  button {
    font: inherit;
  }

  .icon-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    margin-left: -8px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }

  .icon-button .icon {
    width: 24px;
    height: 24px;
  }

  .toolbar-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border: 1px solid currentColor;
    border-radius: 18px;
    background: transparent;
    color: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }

  .icon-button:hover,
  .toolbar-button:hover {
    background: rgba(127, 127, 127, 0.18);
  }

  .content {
    box-sizing: border-box;
    max-width: 1400px;
    margin: 0 auto;
    padding: 16px;
  }

  :host([narrow]) .content {
    padding: 8px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 16px;
    align-items: start;
  }

  :host([narrow]) .grid {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .card {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 16px 8px;
  }

  .heading {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 500;
    overflow-wrap: anywhere;
  }

  .is-disabled h2 {
    color: var(--secondary-text-color, #727272);
  }

  .badge,
  .chip {
    display: inline-block;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    line-height: 18px;
    white-space: nowrap;
  }

  .badge {
    padding: 1px 8px;
    color: var(--secondary-text-color, #727272);
    background: rgba(127, 127, 127, 0.15);
  }

  .badge.ok {
    color: var(--success-color, #43a047);
    background: rgba(var(--rgb-success-color, 67, 160, 71), 0.15);
  }

  .badge.info {
    color: var(--info-color, #039be5);
    background: rgba(var(--rgb-info-color, 3, 155, 229), 0.15);
  }

  .badge.warn {
    color: var(--warning-color, #ffa600);
    background: rgba(var(--rgb-warning-color, 255, 166, 0), 0.18);
  }

  .badge.error {
    color: var(--error-color, #db4437);
    background: rgba(var(--rgb-error-color, 219, 68, 55), 0.15);
  }

  .chip {
    margin-left: 4px;
    padding: 0 6px;
    border: 1px solid var(--divider-color, #e0e0e0);
    color: var(--secondary-text-color, #727272);
  }

  .chip.warn {
    border-color: var(--warning-color, #ffa600);
    color: var(--warning-color, #ffa600);
  }

  .switch {
    position: relative;
    display: inline-flex;
    flex: none;
    cursor: pointer;
  }

  .switch input {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: 0;
    opacity: 0;
  }

  .track {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: var(--switch-unchecked-track-color, rgba(127, 127, 127, 0.45));
    transition: background 0.2s;
  }

  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--switch-unchecked-button-color, #fafafa);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
    transition: transform 0.2s;
  }

  .switch input:checked + .track {
    background: var(--switch-checked-track-color, var(--primary-color, #03a9f4));
  }

  .switch input:checked + .track .thumb {
    transform: translateX(16px);
    background: var(--switch-checked-button-color, #fff);
  }

  .switch input:disabled + .track {
    opacity: 0.5;
  }

  .switch input:focus-visible + .track,
  button:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 2px;
  }

  .running-block {
    margin: 0 16px 8px;
    padding: 10px 12px;
    border-radius: 8px;
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.12);
  }

  .running-title {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    color: var(--primary-color, #03a9f4);
    font-weight: 500;
  }

  .running-zone {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
  }

  .countdown {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .rows {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    column-gap: 16px;
    row-gap: 10px;
    margin: 0;
    padding: 4px 16px 12px;
    font-size: 14px;
    line-height: 20px;
  }

  dt {
    color: var(--secondary-text-color, #727272);
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--secondary-text-color, #727272);
  }

  .detail.warn {
    color: var(--warning-color, #ffa600);
  }

  .detail.error,
  .zone-list li.error {
    color: var(--error-color, #db4437);
  }

  .detail.muted {
    color: var(--secondary-text-color, #727272);
  }

  .zone-list {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .zone-list li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .zone-list .zone-error {
    display: block;
    font-size: 13px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: auto;
    padding: 12px 16px 16px;
    border-top: 1px solid var(--divider-color, #e0e0e0);
  }

  .spacer {
    flex: 1;
  }

  .action {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border: none;
    border-radius: 18px;
    background: transparent;
    color: var(--primary-color, #03a9f4);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }

  .action:hover {
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
  }

  .action.filled {
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }

  .action.danger {
    background: var(--error-color, #db4437);
    color: #fff;
  }

  .action.filled:hover,
  .action.danger:hover {
    filter: brightness(1.08);
  }

  .action:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .icon {
    width: 18px;
    height: 18px;
    flex: none;
    fill: currentColor;
  }

  .banner {
    margin-bottom: 16px;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 14px;
  }

  .banner.error {
    color: var(--error-color, #db4437);
    background: rgba(var(--rgb-error-color, 219, 68, 55), 0.12);
  }

  .card-banner {
    margin: 0 16px 12px;
  }

  .empty {
    padding: 48px 16px;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }

  .empty h2 {
    margin: 8px 0;
    color: var(--primary-text-color, #212121);
  }

  .empty p {
    max-width: 420px;
    margin: 0 auto 16px;
  }

  .empty-icon .icon {
    width: 48px;
    height: 48px;
    color: var(--primary-color, #03a9f4);
  }

  .banner.warn {
    color: var(--warning-color, #ffa600);
    background: rgba(var(--rgb-warning-color, 255, 166, 0), 0.14);
  }

  .banner .icon {
    margin-right: 6px;
    vertical-align: -3px;
  }

  .global-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
    margin-bottom: 12px;
  }

  .inline-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
  }

  .mini {
    padding: 2px 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 12px;
    background: transparent;
    color: var(--primary-color, #03a9f4);
    font-size: 13px;
    line-height: 18px;
    cursor: pointer;
  }

  .mini:hover {
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
  }

  .mini:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .zone-controls {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }

  .history-list {
    display: grid;
    gap: 2px;
    margin: 0 0 4px;
    padding: 0;
    list-style: none;
  }

  .history-list li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .history-list li.error {
    color: var(--error-color, #db4437);
  }

  .detail.ok {
    color: var(--success-color, #43a047);
  }

  .detail.info {
    color: var(--info-color, #039be5);
  }

  .check-block {
    margin: 0 16px 12px;
    padding: 10px 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    font-size: 14px;
    line-height: 20px;
  }

  .check-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
    font-weight: 500;
  }

  .icon-button.small {
    width: 28px;
    height: 28px;
    margin: -4px -6px -4px 0;
    color: var(--secondary-text-color, #727272);
  }

  .icon-button.small .icon {
    width: 18px;
    height: 18px;
  }

  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(0, 0, 0, 0.45);
  }

  .dialog {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    width: min(640px, 100%);
    max-height: calc(100vh - 32px);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
    border-radius: var(--ha-dialog-border-radius, 16px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }

  .dialog h2 {
    padding: 20px 24px 8px;
  }

  .dialog-text {
    padding: 0 24px;
    overflow: auto;
    white-space: pre-wrap;
    font-size: 14px;
    line-height: 21px;
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    padding: 16px 24px 20px;
  }

  @media (max-width: 450px) {
    .rows {
      grid-template-columns: minmax(0, 1fr);
      row-gap: 2px;
    }

    dt:not(:first-child) {
      margin-top: 8px;
    }

    .toolbar-button span {
      display: none;
    }
  }
`;

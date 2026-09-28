"use strict";

const outcomes = [
  ["Approved", "Simulated approval response."],
  ["Declined", "Simulated decline response."],
  ["Authentication required", "Simulated step-up authentication response."],
];

const results = document.querySelector("#results");

document.querySelector("#runDemo").addEventListener("click", () => {
  results.replaceChildren();
  for (const [label, detail] of outcomes) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    const description = document.createElement("span");
    title.textContent = label;
    description.textContent = detail;
    item.append(title, description);
    results.append(item);
  }
});

document.querySelector("#clearDemo").addEventListener("click", () => {
  results.replaceChildren();
});

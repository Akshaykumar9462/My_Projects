"use strict";

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const input = document.getElementById(button.dataset.target);
        if (!input) return;

        button.addEventListener("click", () => {
            const showPassword = input.type === "password";
            input.type = showPassword ? "text" : "password";
            button.textContent = showPassword ? "Hide" : "Show";
            button.setAttribute("aria-pressed", String(showPassword));
            button.setAttribute(
                "aria-label",
                `${showPassword ? "Hide" : "Show"} ${button.dataset.label}`,
            );
        });
    });

    const matchMessage = document.querySelector("[data-password-match]");
    if (!matchMessage) return;

    const password = document.getElementById(matchMessage.dataset.passwordId);
    const confirmation = document.getElementById(matchMessage.dataset.confirmId);
    if (!password || !confirmation) return;

    const updatePasswordMatch = () => {
        if (!confirmation.value) {
            matchMessage.textContent = "Enter the confirmation password to check for a match.";
            matchMessage.dataset.state = "empty";
            return;
        }

        const passwordsMatch = password.value === confirmation.value;
        matchMessage.textContent = passwordsMatch
            ? "Passwords match."
            : "Passwords do not match.";
        matchMessage.dataset.state = passwordsMatch ? "match" : "mismatch";
    };

    password.addEventListener("input", updatePasswordMatch);
    confirmation.addEventListener("input", updatePasswordMatch);
    updatePasswordMatch();
});


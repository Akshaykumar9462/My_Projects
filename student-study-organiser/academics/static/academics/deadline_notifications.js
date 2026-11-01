"use strict";

(() => {
    const enableButton = document.getElementById("enable-deadline-notifications");
    const statusMessage = document.getElementById("notification-status");

    if (!enableButton || !statusMessage) {
        return;
    }

    if (!("Notification" in window)) {
        enableButton.disabled = true;
        statusMessage.textContent = "This browser does not support desktop notifications.";
        return;
    }

    function showUpcomingReminders() {
        if (Notification.permission !== "granted") {
            return;
        }

        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const rows = document.querySelectorAll(".task-row[data-task-due]");
        let remindersShown = 0;

        rows.forEach((row) => {
            if (row.dataset.taskStatus === "completed" || !row.dataset.taskDue) {
                return;
            }

            const [year, month, day] = row.dataset.taskDue.split("-").map(Number);
            const dueDate = new Date(year, month - 1, day);
            const daysUntilDue = Math.round((dueDate - today) / 86400000);
            if (daysUntilDue < 0 || daysUntilDue > 1) {
                return;
            }

            const reminderKey = `study-organiser-${row.dataset.taskId}-${row.dataset.taskDue}`;
            if (window.localStorage.getItem(reminderKey)) {
                return;
            }

            const timing = daysUntilDue === 0 ? "Due today" : "Due tomorrow";
            new Notification(`Study Organiser: ${timing}`, {
                body: row.dataset.taskTitle,
                tag: reminderKey,
            });
            window.localStorage.setItem(reminderKey, "shown");
            remindersShown += 1;
        });

        if (remindersShown) {
            statusMessage.textContent = `Shown ${remindersShown} deadline reminder${remindersShown === 1 ? "" : "s"}.`;
        } else {
            statusMessage.textContent = "No new tasks are due today or tomorrow.";
        }
    }

    if (Notification.permission === "granted") {
        enableButton.textContent = "Check upcoming reminders";
        showUpcomingReminders();
    } else if (Notification.permission === "denied") {
        enableButton.disabled = true;
        statusMessage.textContent = "Notifications are blocked for this site. Change the permission in your browser settings to enable them.";
    }

    enableButton.addEventListener("click", async () => {
        const permission = await Notification.requestPermission();
        if (permission === "granted") {
            enableButton.textContent = "Check upcoming reminders";
            showUpcomingReminders();
        } else {
            statusMessage.textContent = "Allow notifications in the browser prompt to receive deadline reminders.";
        }
    });
})();


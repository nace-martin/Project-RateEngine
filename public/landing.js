document.addEventListener("DOMContentLoaded", function() {
    const logoutButton = document.getElementById("logout-button");

    if (logoutButton) {
        logoutButton.addEventListener("click", function(event) {
            event.preventDefault();

            // You can add more complex logout logic here, like clearing session storage
            window.location.href = "login.html";
        });
    }
});

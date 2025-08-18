document.addEventListener("DOMContentLoaded", function() {
    const loginForm = document.getElementById("login-form");

    if (loginForm) {
        loginForm.addEventListener("submit", function(event) {
            event.preventDefault();

            const username = event.target.username.value;
            const password = event.target.password.value;

            // Hardcoded username and password for demonstration purposes
            if (username === "admin" && password === "password") {
                window.location.href = "landing.html";
            } else {
                alert("Invalid username or password");
            }
        });
    }
});

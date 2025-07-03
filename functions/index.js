const functions = require("firebase-functions");
const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

// Read the HTML template from the file system
const quoteTemplateHtml = fs.readFileSync(path.resolve(__dirname, "templates/quoteTemplate.html"), "utf8");

/**
 * Replaces placeholders in the HTML template with actual data.
 * @param {string} template The HTML template string.
 * @param {object} data The quote data object.
 * @return {string} The HTML string with data injected.
 */
const populateTemplate = (template, data) => {
    let populatedHtml = template;
    for (const [key, value] of Object.entries(data)) {
        const regex = new RegExp(`{{${key}}}`, "g");
        populatedHtml = populatedHtml.replace(regex, value);
    }
    return populatedHtml;
};

exports.generateQuotePdf = functions.https.onRequest({ region: "australia-southeast1" }, async (req, res) => {
    if (req.method !== "POST") {
        res.status(405).send("Method Not Allowed");
        return;
    }

    const quoteData = req.body;

    // Basic validation
    if (!quoteData || typeof quoteData !== "object") {
        res.status(400).send("Bad Request: No data received.");
        return;
    }

    try {
        const htmlContent = populateTemplate(quoteTemplateHtml, quoteData);

        const browser = await puppeteer.launch({
            headless: true,
            args: ["--no-sandbox", "--disable-setuid-sandbox"],
        });
        const page = await browser.newPage();

        await page.setContent(htmlContent, { waitUntil: "networkidle0" });

        const pdfBuffer = await page.pdf({
            format: "A4",
            printBackground: true,
            margin: {
                top: "20px",
                right: "20px",
                bottom: "20px",
                left: "20px",
            },
        });

        await browser.close();

        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Content-Disposition", `attachment; filename=quote-${quoteData.quoteId || "download"}.pdf`);
        res.status(200).send(pdfBuffer);

    } catch (error) {
        console.error("Error generating PDF:", error);
        res.status(500).send("Internal Server Error: Could not generate PDF.");
    }
});

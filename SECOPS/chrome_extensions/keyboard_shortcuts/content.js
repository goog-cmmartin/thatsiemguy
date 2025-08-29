// content.js
let altPressed = false;
let shiftPressed = false;
let toast;

async function insertModal() {
  try {
    // Fetch the HTML template
    const response = await fetch(chrome.runtime.getURL('modal.html'));
    const html = await response.text();

    //Fetch the css Stylesheet
    const cssResponse = await fetch(chrome.runtime.getURL('styles.css'));
    const css = await cssResponse.text();

    // Create style element
    const style = document.createElement('style');
    style.textContent = css;

    // Inject the HTML into the page
    document.body.insertAdjacentHTML('beforeend', html);
    document.head.appendChild(style); // Inject CSS styles

    // Set the image source
    const iconUrl = chrome.runtime.getURL('icon48.png');
    document.getElementById('modalIcon').src = iconUrl;

    // Get the extension's manifest
    const manifest = chrome.runtime.getManifest();
    const version = manifest.version;

    const versionElement = document.getElementById("modalVersion");
    if (versionElement) {
        versionElement.innerHTML = `<b>Version</b>: ${version}`;
    }

    // Create the toast element
    toast = document.createElement("div");
    toast.id = "toast";
    document.body.appendChild(toast);

    // Add event listener to close the modal when clicking outside
    document.getElementById("shortcutOverlay").addEventListener("click", function (event) {
      if (event.target.id === "shortcutOverlay") {
        closeModal();
      }
    });

    // Add event listener to the close button
    document.getElementById("closeModalButton").addEventListener("click", function () {
      closeModal();
    });

    // Add event listener for the Escape key
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeModal();
      }
    });

    // ✨ ADDED: Add event listener for the search input
    const searchInput = document.getElementById("shortcutSearchInput");
    searchInput.addEventListener("input", function () {
      populateModal(shortcutActions, this.value);
    });


  } catch (error) {
    console.error("Error inserting modal:", error);
  }
}

function closeModal() {
  document.getElementById("shortcutModal").style.display = "none";
  document.getElementById("shortcutOverlay").style.display = "none";
}


// Function to show the toast
function showToast(message) {
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = 1;
  setTimeout(() => {
    toast.style.opacity = 0;
  }, 1500); // Hide after 1.5 seconds
}

// balance content across two columns
function populateModal(shortcuts, searchTerm = "") {
    const list = document.querySelector("#shortcutModal ul");
    list.innerHTML = ""; // Clear previous content

    const lowerCaseSearchTerm = searchTerm.toLowerCase().trim();
    let shortcutsToDisplay = shortcuts;

    // Filter shortcuts based on search term
    if (lowerCaseSearchTerm) {
        shortcutsToDisplay = Object.entries(shortcuts)
            .filter(([key, shortcut]) => {
                const descriptionMatch = shortcut.description.toLowerCase().includes(lowerCaseSearchTerm);
                const keyMatch = `alt+shift+${key}`.toLowerCase().includes(lowerCaseSearchTerm);
                const categoryMatch = shortcut.category.toLowerCase().includes(lowerCaseSearchTerm);
                return descriptionMatch || keyMatch || categoryMatch;
            })
            .reduce((obj, [key, shortcut]) => {
                obj[key] = shortcut;
                return obj;
            }, {});
    }

    // Group shortcuts by category
    const groupedShortcuts = {};
    for (const key in shortcutsToDisplay) {
        const shortcut = shortcutsToDisplay[key];
        if (!groupedShortcuts[shortcut.category]) {
            groupedShortcuts[shortcut.category] = [];
        }
        groupedShortcuts[shortcut.category].push({ key, ...shortcut });
    }

    // If no results, show a message
    if (Object.keys(groupedShortcuts).length === 0) {
        list.innerHTML = `<li style="text-align: center; display: block; list-style: none;">No shortcuts found.</li>`;
        return;
    }

    const container = document.createElement('div');
    container.id = 'shortcutListContainer';

    const column1 = document.createElement('div');
    column1.className = 'shortcut-column';
    const column1Ul = document.createElement('ul'); // Create a UL for shortcuts in column 1
    column1.appendChild(column1Ul);

    const column2 = document.createElement('div');
    column2.className = 'shortcut-column';
    const column2Ul = document.createElement('ul'); // Create a UL for shortcuts in column 2
    column2.appendChild(column2Ul);

    let currentColumn = column1Ul;
    let otherColumn = column2Ul;

    // Get all categories and sort them (optional, but can help with consistency)
    const categories = Object.keys(groupedShortcuts).sort();

    // Iterate through each category
    categories.forEach(category => {
        const categoryHeading = document.createElement("h3");
        categoryHeading.textContent = category;

        // Determine which column to add the category heading to
        // This simple check tries to balance based on approximate content height (number of lines)
        const column1Height = column1.querySelectorAll('li').length + column1.querySelectorAll('h3').length;
        const column2Height = column2.querySelectorAll('li').length + column2.querySelectorAll('h3').length;

        if (column1Height <= column2Height) {
            currentColumn = column1Ul;
            otherColumn = column2Ul;
        } else {
            currentColumn = column2Ul;
            otherColumn = column1Ul;
        }
        
        currentColumn.appendChild(categoryHeading);

        // Append shortcuts of this category to the chosen column
        groupedShortcuts[category].forEach(shortcut => {
            const item = document.createElement("li");
            const descriptionSpan = document.createElement("span");
            descriptionSpan.textContent = shortcut.description;
            const preElement = document.createElement("pre");
            preElement.textContent = `Alt+Shift+${shortcut.key}`;
            item.appendChild(descriptionSpan);
            item.appendChild(preElement);
            currentColumn.appendChild(item);
        });
    });

    container.appendChild(column1);
    container.appendChild(column2);

    // Append the final container to the main list element
    list.appendChild(container);
}


document.addEventListener("keydown", function (event) {
  if (event.code === "AltLeft") {
    altPressed = true;
  }
  if (event.code === "ShiftLeft") {
    shiftPressed = true;
  }

  // Ignore key presses if the search input is focused
  if (document.activeElement.id === 'shortcutSearchInput') {
    return;
  }

  if (altPressed && shiftPressed && event.code === "Slash") { // "?" requires shift, so use Slash
    const searchInput = document.getElementById("shortcutSearchInput");
    searchInput.value = "";
    populateModal(shortcutActions);
    document.getElementById("shortcutModal").style.display = "block";
    document.getElementById("shortcutOverlay").style.display = "block";
    searchInput.focus(); // Automatically focus the search bar

    altPressed = false;
    shiftPressed = false;
  } else if (altPressed && shiftPressed && shortcutActions[event.code]) {
    const action = shortcutActions[event.code].action;
    const description = shortcutActions[event.code].description;

    console.log(`Alt+Shift+${event.code} sequence detected: ${description}`);
    showToast(`Alt+Shift+${event.code} Pressed`);
    action();

    altPressed = false;
    shiftPressed = false;
  }
});

document.addEventListener("keyup", function (event) {
  if (event.code === "AltLeft") { // or AltRight
    altPressed = false;
  }
  if (event.code === "ShiftLeft") { // or ShiftRight
    shiftPressed = false;
  }
});

/**
 * Finds the header actions container and inserts a custom button
 * that opens the shortcuts modal.
 */
function addButtonToHeader() {
  const headerActionsContainer = document.querySelector('sc-navigation-header-actions');
  const userProfileButton = document.querySelector('#user-actions');

  // We need both the container and the user button to place our new button correctly
  if (headerActionsContainer && userProfileButton) {
    // Check if our button already exists to avoid adding it multiple times
    if (headerActionsContainer.querySelector('.secops-shortcuts-header-button')) {
      return;
    }

    const myButton = document.createElement('button');
    myButton.setAttribute('role', 'button');
    // Use a more specific class name
    myButton.className = 'secops-shortcuts-header-button smp-transition';
    myButton.ariaLabel = "Open SecOps Shortcuts";
    myButton.title = "Open SecOps Shortcuts (Alt+Shift+?)"; // Adds a helpful tooltip

    // ✨ Create an <img> element for our icon
    const iconImage = document.createElement('img');
    iconImage.src = chrome.runtime.getURL('icon48.png');

    // ✨ Style the icon to fit in with the others (usually 24px)
    iconImage.style.width = '24px';
    iconImage.style.height = '24px';
    iconImage.style.verticalAlign = 'middle'; // Helps with alignment

    // Add the image to the button
    myButton.appendChild(iconImage);

    // Copy styles to make it look like a native button
    myButton.style.backgroundColor = 'transparent';
    myButton.style.border = 'none';
    myButton.style.cursor = 'pointer';
    myButton.style.padding = '8px';
    myButton.style.borderRadius = '50%'; // Most icon buttons are circular

    // ✨ Make the button open the shortcuts modal
    myButton.addEventListener('click', () => {
      const searchInput = document.getElementById("shortcutSearchInput");
      if (searchInput) {
        searchInput.value = "";
      }
      populateModal(shortcutActions);
      document.getElementById("shortcutModal").style.display = "block";
      document.getElementById("shortcutOverlay").style.display = "block";
      if (searchInput) {
        searchInput.focus();
      }
    });

    // Insert our new button before the user profile button
    headerActionsContainer.insertBefore(myButton, userProfileButton);
  }
}

// --- The MutationObserver to wait for the header ---

const headerObserver = new MutationObserver((mutationsList, observer) => {
  const headerActions = document.querySelector('sc-navigation-header-actions');

  if (headerActions) {
    console.log("Header actions container found. Injecting shortcuts icon.");
    addButtonToHeader();
    observer.disconnect(); // Stop observing once we've added the button
  }
});

// Start observing the document body for added elements
headerObserver.observe(document.body, { childList: true, subtree: true });

const shortcutActions = {
    "Digit1": { description: "Open SOAR Cases", category: "Navigation", action: () => window.location.href = `${window.location.origin}/cases` },
    "Digit2": { description: "Open SOAR Workdesk", category: "Navigation", action: () => window.location.href = `${window.location.origin}/your-workdesk` },
    "Digit3": { description: "Open SIEM Search", category: "Navigation", action: () => window.location.href = `${window.location.origin}/search` },
    "Digit4": { description: "Open SOAR Search", category: "Navigation", action: () => window.location.href = `${window.location.origin}/sp-search` },
    "Digit5": { description: "Open SIEM Data Tables", category: "Navigation", action: () => window.location.href = `${window.location.origin}/data-tables` },
    "Digit6": { description: "Open SIEM Rule Editor", category: "Navigation", action: () => window.location.href = `${window.location.origin}/rulesEditor` },
    "Digit7": { description: "Open SIEM Native Dashboards", category: "Navigation", action: () => window.location.href = `${window.location.origin}/dashboards-v2` },
    "Digit8": { description: "Open SecOps Marketplace", category: "Navigation", action: () => window.location.href = `${window.location.origin}/marketplace` },
    "Digit9": { description: "Open SIEM Settings", category: "Navigation", action: () => window.location.href = `${window.location.origin}/settings` },
    "Digit0": { description: "Open SOAR Settings", category: "Navigation", action: () => window.location.href = `${window.location.origin}/sp-settings` },
    "KeyA": { description: "Toggle Aggregation panel", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#fields-aggregations").shadowRoot.querySelector("mc-widget-container").shadowRoot.querySelector("#toggle").shadowRoot.querySelector("#left-icon")?.click() },
    "KeyC": { description: "Collapse or Expand all panels", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#header").shadowRoot.querySelector("#toggle").shadowRoot.querySelector("button")?.click() },
    "KeyE": { description: "Expand / Collapse Event Fields", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#events > swc-polymer-to-angular-bridge").shadowRoot.querySelector("*:nth-child(2) > sc-udm-fields-widget > sc-widget-container > sc-resizer > div.resizable-content > section > div > div > sc-fetch-status > sc-udm-fields-viewer > div.udm-fields-selection.ng-star-inserted > button")?.click() },
    "KeyF": { description: "Toggle Filter modal", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#filter-bar > mc-filter-bar").shadowRoot.querySelector("#new-filter-trigger")?.click() },
    "KeyG": { description: "Toggle Gemini side panel", category: "Navigation", action: () => document.querySelector("body > app-root > siem-main-layout > sc-navigation > sc-navigation-header > section > sc-navigation-header-actions > div > button")?.click() },
    "KeyL": { description: "Toggle Saved Column layouts", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#event-timeline").shadowRoot.querySelector("#search-column-selector-button")?.click() },
    "KeyM": { description: "Toggle Trend, Prevalence, & Activity heatmap panel", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#event-count-chart").shadowRoot.querySelector("#toggle").shadowRoot.querySelector("#left-icon")?.click() },
    "KeyU": { description: "Open UDM Lookup modal", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#header > div > mc-query-controls").shadowRoot.querySelector("#query-controls-buttons-row-bridge").shadowRoot.querySelector("#query-controls-buttons-row > div.left-buttons > div:nth-child(2) > button")?.click() },
    "KeyW": { description: "Wrap or Unwrap Text", category: "UDM Search", action: () => document.querySelector("#siem-main-content > smp-legacy-malachite > mc-app").shadowRoot.querySelector("#pages > swc-search > mc-view-search").shadowRoot.querySelector("#event-timeline").shadowRoot.querySelector("#word-wrap")?.click() },
    "KeyN": { description: "Toggle Comments modal", category: "SOAR", action: () => document.querySelector("#siem-main-content > cases-page > cases-dynamic-layout > smp-layout > div > div > div > smp-layout-content > cases-dynamic-command-line > cases-command-line > div.right > button:nth-child(2)")?.click() },
};

// Call insertModal on page load
insertModal();
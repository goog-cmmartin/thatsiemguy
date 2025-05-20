(function() {
  // Configuration: These values are placeholders and should be configured externally
  // or replaced by a proper configuration mechanism when deploying this widget.
  const DEFAULT_SECOPS_URL = "https://go-preview-americas-sdl.backstory.chronicle.security";
  const DEFAULT_ENTITY_FILTER = ["THREAT", "THREATSIGNATURE", "EMAILSUBJECT"];

  document.addEventListener("DOMContentLoaded", (event) => {
    const htmlElement = document.documentElement;
    const switchElement = document.getElementById("darkModeSwitch");

    // Set the default theme to dark if no setting is found in local storage
    const currentTheme = localStorage.getItem("bsTheme") || "dark";
    htmlElement.setAttribute("data-bs-theme", currentTheme);
    switchElement.checked = currentTheme === "dark";

    switchElement.addEventListener("change", function() {
      if (this.checked) {
        htmlElement.setAttribute("data-bs-theme", "dark");
        localStorage.setItem("bsTheme", "dark");
      } else {
        htmlElement.setAttribute("data-bs-theme", "light");
        localStorage.setItem("bsTheme", "light");
      }
    });
  });

  // In your JavaScript code
  const getSelectedRowsButton =
    document.getElementById("get-selected-rows");

  getSelectedRowsButton.addEventListener("click", () => {
    const selectedRows = table.getSelectedData();

    // Get the selected logic from the button's text content
    const selectedLogic = document
      .getElementById("logicDropdown")
      .textContent.trim();

    // Get the dropdown menu element
    // const dropdownMenu = document.querySelector(".dropdown-menu"); // This line seems unused
    const pivotLink = generateCompoundUdmSearchUrl(selectedRows, selectedLogic);

    if (pivotLink) {
      window.open(pivotLink, "_blank");
    } else {
      console.warn("No valid pivot link could be generated for the selected entities.");
    }
  });

  // Get the dropdown menu and the button
  const dropdownMenu = document.querySelector(".dropdown-menu");
  const dropdownButton = document.getElementById("logicDropdown");

  // Add an event listener to the dropdown menu
  dropdownMenu.addEventListener("click", (event) => {
    // Prevent default link behavior
    event.preventDefault();

    // Get the selected logic condition
    const selectedLogic = event.target.dataset.logic;

    // Update the button text
    dropdownButton.textContent = selectedLogic;

    // Do something with the selected logic (e.g., update your query builder)
    // console.log("Selected logic:", selectedLogic);
  });

  function generateCompoundUdmSearchUrl(data, logic) {
    // Handle single row data (backward compatibility)
    if (!Array.isArray(data)) {
      const rowData = data;
      const {
        CreationTime,
        EntityCards: { SourceSystemUrl, Identifier, Type },
      } = rowData;

      const queryParam = getQuery(Identifier, Type);
      // Check if the Type is supported
      if (!queryParam) {
        return null; // Return null if not supported.
      }
      
      const { startTimeIso, endTimeIso } = convertTimestamps(
        CreationTime,
        CreationTime
      );
      return `${SourceSystemUrl}/search?query=${encodeURIComponent(
          queryParam
        )}&startTime=${startTimeIso}&endTime=${endTimeIso}`;
    }
    // Handle multiple rows with AND/OR logic
    else {
      let queryParams = [];
      let validRows = []; // Store only valid rows for processing
      for (const row of data) {
        const {
          EntityCards: { Identifier, Type },
        } = row;
        
        const queryParam = getQuery(Identifier, Type);
        // Check if the type is supported. if not, dont add to the array for URL processing.
        if (queryParam) {
          queryParams.push(queryParam);
          validRows.push(row)
        }
      }

      if (validRows.length === 0) return null; // If no rows have valid types, dont return a link.

      const combinedQueryParam = queryParams.join(
        logic === "AND" ? " AND " : " OR "
      );
      const firstRow = validRows[0]; // Use the first VALID row data.
      const {
        EntityCards: { SourceSystemUrl },
      } = firstRow;
      const { CreationTime } = firstRow;
      const { startTimeIso, endTimeIso } = convertTimestamps(
        CreationTime,
        CreationTime
      );
      return `${SourceSystemUrl}/search?query=${encodeURIComponent(
          combinedQueryParam
        )}&startTime=${startTimeIso}&endTime=${endTimeIso}`;
    }
  }

  function createSearchAnchorElement(
    SourceSystemUrl,
    queryParam,
    startTimeIso,
    endTimeIso
  ) {
    const formattedValue = `${SourceSystemUrl}/search?query=${encodeURIComponent(
          queryParam
        )}&startTime=${startTimeIso}&endTime=${endTimeIso}`;
    const link = document.createElement("a");
    link.href = formattedValue;
    link.innerHTML = "Run" + " " + svg_open;
    link.classList.add("btn", "btn-success");
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  function getQuery(identifier, entityType) {
    const queryTemplates = {
      ADDRESS: "ip = {{identifier}} nocase",
      DOMAIN: "domain = {{identifier}} nocase",
      HOSTNAME: "hostname = {{identifier}} nocase",
      USERUNIQNAME: "( user = {{identifier}} nocase OR email = {{identifier}} nocase )",
      PROCESS: "process_id = {{identifier}} nocase",
      FILENAME: "file_path = {{identifier}} nocase",
      FILEHASH: "hash = {{identifier}} nocase",
    };

    const template = queryTemplates[entityType];

    if (template) {
      return template.replace(
        /\{\{identifier\}\}/g,
        JSON.stringify(identifier)
      );
    } else {
      return null; // Return null if the entity type is not supported
    }
  }

  function convertTimestamps(oldestTime, latestTime) {
    // Convert timestamps from milliseconds to seconds
    const startTimeSeconds = oldestTime / 1000;
    const endTimeSeconds = latestTime / 1000;

    // Calculate start and end times with 1 day offset
    const startTime = new Date(startTimeSeconds * 1000);
    // Adjust time range: +/- 1 day from the event's CreationTime to capture related events and account for potential minor clock skews.
    startTime.setDate(startTime.getDate() - 1); // Subtract 1 day

    let endTime = new Date(endTimeSeconds * 1000); // Use 'let' instead of 'const'
    // Adjust time range: +/- 1 day from the event's CreationTime to capture related events and account for potential minor clock skews.
    endTime.setDate(endTime.getDate() + 1); // Add 1 day

    // Ensure end time is not in the future
    const now = new Date();
    endTime = endTime > now ? now : endTime; // Now you can reassign endTime

    // Format timestamps as ISO strings with milliseconds and 'Z' for UTC
    const startTimeIso = startTime.toISOString().replace("+00:00", "Z");
    const endTimeIso = endTime.toISOString().replace("+00:00", "Z");

    return { startTimeIso, endTimeIso };
  }

  // Open in new windows SVG Icon
  const svg_open = `<svg width="16" height="16" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M17.444 17.444H6.555V6.556H12V5H6.555C5.692 5 5 5.7 5 6.556v10.888C5 18.3 5.692 19 6.555 19h10.889c.855 0 1.555-.7 1.555-1.556V12h-1.555v5.444z"></path><path d="M13.556 5v1.556h2.792L8.703 14.2l1.096 1.097 7.646-7.646v2.792H19V5h-5.444z"></path></svg>`;

  function createUdmLink(cell, formatterParams, onRendered) {
    const rowData = cell.getRow().getData();
    const {
      CreationTime,
      EntityCards: { SourceSystemUrl, Identifier, Type },
    } = rowData;

    const queryParam = getQuery(Identifier, Type);
    
    // Check if the Type is supported
    if (!queryParam) {
      const link = document.createElement("a");
      link.classList.add("btn", "btn-secondary");
      link.setAttribute("disabled", "");
      link.setAttribute("aria-disabled", "true");
      link.innerHTML = "Run" + " " + svg_open;
      link.title = "UDM pivot not available for this entity type.";
      return link; 
    }

    // Directly use CreationTime for both start and end times
    const { startTimeIso, endTimeIso } = convertTimestamps(
      CreationTime,
      CreationTime
    );

    return createSearchAnchorElement(SourceSystemUrl, queryParam, startTimeIso, endTimeIso);
  }


  function createRlsLink(cell, formatterParams, onRendered) {
    const rowData = cell.getRow().getData();
    const {
      CreationTime,
      EntityCards: { SourceSystemUrl, Identifier },
    } = rowData;

    // Directly use CreationTime for both start and end times
    const { startTimeIso, endTimeIso } = convertTimestamps(
      CreationTime,
      CreationTime
    );

    const formattedValue = `${SourceSystemUrl}/search?query=raw%20%3D%20%2F%28%3Fi%29${encodeURIComponent(
          JSON.stringify(Identifier).slice(1, -1).replace(/\\/g, '\\\\')
        )}%2F&startTime=${startTimeIso}&endTime=${endTimeIso}`;

    const link = document.createElement("a");
    link.href = formattedValue;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.innerHTML = "Run" + " " + svg_open;
    link.classList.add("btn", "btn-primary");
    // link.target = "_blank"; // Duplicate target="_blank" was here, removed one.

    return link;
  }

  function buildJsonObject() { // Removed 'filter' parameter as it will use DEFAULT_ENTITY_FILTER
    // The following lines expect placeholder strings like "[Entity.Identifier]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesIdentifier =
      String.raw`[Entity.Identifier]`.split(
        ","
      );
    // The following lines expect placeholder strings like "[Entity.Type]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesType =
      "[Entity.Type]".split(
        ","
      );
    // The following lines expect placeholder strings like "[Entity.IsInternalAsset]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesInternal = "[Entity.IsInternalAsset]".split(
      ","
    );
    // The following lines expect placeholder strings like "[Entity.IsSuspicious]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesSuspicious =
      "[Entity.IsSuspicious]".split(",");
    // The following lines expect placeholder strings like "[Entity.IsPivot]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesPivot = "[Entity.IsPivot]".split(
      ","
    );
    // The following lines expect placeholder strings like "[Entity.IsManuallyCreated]" to be replaced by actual, comma-separated data by a server-side process or templating engine.
    const entitiesManual = "[Entity.IsManuallyCreated]".split(
      ","
    );
    
    // The following line expects a placeholder string like "[Alert.CreationTime]" to be replaced by an actual timestamp by a server-side process or templating engine.
    const date = new Date("[Alert.CreationTime]");

    // Get the timestamp in milliseconds
    const timestampMilis = date.getTime(); //* 1000;

    return entitiesIdentifier
      .map((identifier, index) => ({
        EntityCards: {
          Identifier: identifier,
          IsInternalAsset: entitiesInternal[index],
          IsPivot: entitiesPivot[index],
          IsSuspicious: entitiesSuspicious[index],
          Type: entitiesType[index],
          SourceSystemUrl: DEFAULT_SECOPS_URL, // Use configurable URL
          IsManuallyCreated: entitiesManual[index],
        },
        CreationTime: timestampMilis,
      }))
      .filter((item) => !DEFAULT_ENTITY_FILTER.includes(item.EntityCards.Type)); // Use configurable filter
  }

  const jsonObject = JSON.stringify(buildJsonObject()); // Call buildJsonObject without arguments

  // Parse the JSON string
  const tabledata = JSON.parse(jsonObject);

  const table = new Tabulator("#entity-table", {
    data: tabledata,
    className: "my-tabulator-table",
    layout: "fitColumns",
    rowHeader: {
      headerSort: false,
      resizable: true,
      frozen: true,
      headerHozAlign: "center",
      hozAlign: "center",
      formatter: "rowSelection",
      titleFormatter: "rowSelection",
      cellClick: function(e, cell) {
        cell.getRow().toggleSelect();
      },
      width: 40
    },
    columns: [{
        title: "Identifier",
        field: "EntityCards.Identifier",
        widthGrow: 4,
        formatter: function(cell, formatterParams, onRendered) {
          const div = document.createElement('div');
          div.style.overflowX = 'auto';
          div.textContent = cell.getValue();
          return div;
        },
      },
      { title: "Type", field: "EntityCards.Type" },
      {
        title: "UDM",
        field: "combined",
        hozAlign: "center",
        formatter: createUdmLink,
      },
      {
        title: "RLS",
        field: "combined",
        hozAlign: "center",
        formatter: createRlsLink,
      },
      {
        title: "Suspicious",
        field: "EntityCards.IsSuspicious",
        formatter: "tickCross",
        hozAlign: "center",
      },
      {
        title: "Pivot",
        field: "EntityCards.IsPivot",
        formatter: "tickCross",
        hozAlign: "center",
      },
      {
        title: "Internal",
        field: "EntityCards.IsInternal",
        formatter: "tickCross",
        hozAlign: "center",
      },
      {
        title: "Created Manually",
        field: "EntityCards.IsManuallyCreated",
        formatter: "tickCross",
        hozAlign: "center",
      },
    ],
  });

  const tooltipTriggerList = document.querySelectorAll(
    '[data-bs-toggle="tooltip"]'
  );
  const tooltipList = [...tooltipTriggerList].map(
    (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl)
  );
})();

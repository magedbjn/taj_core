### Taj Core

Core Customizations and common utilities for Taj ERPNext implementation

## Features

- **Override**
  - Party Specific Item: Prevent duplicate entries  

- **Enhancement**
  - Material Request: Function to collect and merge similar items  
  - Expense Claim: Automatically updates Expense Claim status to `Paid` on payment submission
    and reverts to `Unpaid` on payment cancellation, with real-time UI updates (Payment Entry or Journal Entry).

- **New Documents**
  - License: Manage company licenses and certificates with expiry date and email notification  
  - Company Policy: Manage company documents


### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app taj_core
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/taj_core
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit



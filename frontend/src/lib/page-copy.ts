export type UserRole = "admin" | "manager" | "sales" | "finance" | undefined;

type BannerCopy = {
  title: string;
  description: string;
  note?: string;
};

const isBusinessRole = (role: UserRole) => role === "sales" || role === "manager";

export function getNewQuoteCopy(role: UserRole): BannerCopy {
  if (role === "admin") {
    return {
      title: "New Quote",
      description: "Create a quote using your company's configured pricing and rules.",
    };
  }

  if (isBusinessRole(role)) {
    return {
      title: "New Quote",
      description: "Create and send a quote to your customer.",
    };
  }

  return {
    title: "New Quote",
    description: "Create a quote using your company's configured pricing.",
  };
}

export function getNewCustomerCopy(role: UserRole): BannerCopy {
  if (role === "admin") {
    return {
      title: "New Customer",
      description: "Add a customer record to your company database.",
    };
  }

  if (isBusinessRole(role)) {
    return {
      title: "New Customer",
      description: "Add a customer to start quoting and managing shipments.",
    };
  }

  return {
    title: "New Customer",
    description: "Add a customer record for your team.",
  };
}

export function getEditCustomerCopy(): BannerCopy {
  return {
    title: "Customer Details",
    description: "Review and update this customer record.",
  };
}

export function getAdminHubCopy(): { title: string; description: string } {
  return {
    title: "Admin Hub",
    description: "Manage users, pricing rules, and system configuration.",
  };
}

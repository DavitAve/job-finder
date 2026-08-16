import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { JobFilters } from "../components/JobFilters";
import type { JobFilters as Filters } from "../lib/jobs";

const initial: Filters = {
  title: "",
  stacks: [],
  excludedCompanies: [],
  location: "all",
  format: "all",
  onlyNew: false,
  resumeMatch: false,
};

function Harness() {
  const [filters, setFilters] = useState(initial);
  return (
    <>
      <JobFilters companies={["Acme", "Other"]} filters={filters} stacks={["React", "Vue"]} onChange={setFilters} />
      <output aria-label="Текущие фильтры">{JSON.stringify(filters)}</output>
    </>
  );
}

describe("JobFilters", () => {
  it("selects multiple technologies and resets every filter", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("checkbox", { name: "React" }));
    await user.click(screen.getByRole("checkbox", { name: "Vue" }));
    await user.click(screen.getByRole("checkbox", { name: "Acme" }));
    await user.type(screen.getByLabelText("Тайтл"), "frontend");
    await user.selectOptions(screen.getByLabelText("Локация"), "armenia");
    await user.selectOptions(screen.getByLabelText("Формат"), "hybrid");

    expect(screen.getByLabelText("Текущие фильтры")).toHaveTextContent(
      '"stacks":["React","Vue"]',
    );
    expect(screen.getByLabelText("Текущие фильтры")).toHaveTextContent(
      '"excludedCompanies":["Acme"]',
    );

    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    expect(screen.getByLabelText("Текущие фильтры")).toHaveTextContent(
      JSON.stringify(initial),
    );
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfigBuilder } from "../src/components/ConfigBuilder";
import { jsonResponse } from "./fixtures";

const CANONICAL = {
  source: { preset: "emri_c" },
  obs: { T: 8 / 12, dt: 5, tdi_gen: 1, use_gpu: true, pad_output: false },
  noise: { add: true, seed: 42 },
  modes: { ell: 2, n_vals: [-1, 0, 1, 2, 3, 4, 5], M_mode: null, N_traj: 5000, mode_select: null },
  statistic: { kind: "semicoherent", options: { N_seg: 12 } },
  space: {
    kind: "intrinsic",
    free: [
      { name: "m1", transform: "log10", lo: 6.3, hi: 6.8 },
      { name: "m2", transform: "log10", lo: 1.7, hi: 2.1 },
      { name: "a", transform: "identity", lo: 0.8, hi: 0.99 },
      { name: "p0", transform: "identity", lo: 7.0, hi: 8.0 },
      { name: "e0", transform: "identity", lo: 0.2, hi: 0.45 },
    ],
    fixed: {},
  },
  sampler: {
    n_seed: 10,
    num_iterations: 5000,
    init_cov: 1e-2,
    print_iter: 10,
    save_every: 500,
    merge_confidence: 0.9,
    alpha: 1000,
    trail_size: 1000,
    boundary_limiting: true,
    use_beta: true,
    integral_num: 100000,
    gamma: 500,
    exclude_scale_z: "inf",
    use_pool: false,
    keep_dead_processes: true,
    seed: 6342,
  },
  seeding: { kind: "internal_lhs", n: 1000, batch_size: 10 },
  out: "",
  pbs: {
    project: "CFP03-CF-051",
    job_name: "emric_s12",
    walltime: "24:00:00",
    gpu_count: 1,
    cuda_module: "cuda12.4/toolkit/12.4.1",
    venv_activate: "/home/svu/e1498138/emri_search_uv/.venv/bin/activate",
    working_directory: "$PBS_O_WORKDIR",
    log_directory: "logs",
    output_path: "",
    python_filename: "run_emri_c_semicoherent.py",
  },
  emrisearch_version: null,
};

const PREVIEW_RESPONSE = {
  config: { ...CANONICAL, out: "/scratch/emri/emri_c_stage1_s12" },
  artifacts: {
    python: { filename: "run_emri_c_semicoherent.py", content: "#!/usr/bin/env python3\nprint('ok')" },
    pbs: { filename: "run_emri_c_semicoherent.pbs", content: "#!/bin/bash\n#PBS -N emric_s12" },
  },
  written_paths: [],
  saved: false,
};

function installFetch() {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ConfigBuilder", () => {
  it("renders the canonical preset and all section labels", async () => {
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(jsonResponse(CANONICAL));

    render(<ConfigBuilder />);

    await waitFor(() => {
      expect(screen.getByText("config builder")).toBeInTheDocument();
    });
    for (const label of ["source", "observation", "search space (intrinsic)", "statistic", "sampler", "output", "pbs"]) {
      expect(screen.getByRole("heading", { level: 3, name: label })).toBeInTheDocument();
    }
    expect(fetchMock).toHaveBeenCalledWith("/api/configs/canonical", expect.anything());
  });

  it("generates and previews both artifacts without execution controls", async () => {
    const fetchMock = installFetch();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(CANONICAL))
      .mockResolvedValueOnce(jsonResponse(PREVIEW_RESPONSE));

    const user = userEvent.setup();
    render(<ConfigBuilder />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate artifacts/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /generate artifacts/i }));

    await waitFor(() => {
      expect(screen.getByText(/#!\/usr\/bin\/env python3/)).toBeInTheDocument();
      expect(screen.getByText(/#!\/bin\/bash/)).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/configs/preview",
      expect.objectContaining({ method: "POST" }),
    );

    // Generate-only surface: no execution/submission/status controls may exist.
    for (const label of [/run now/i, /^submit$/i, /queue/i, /cancel/i, /status/i]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });

  it("renders a validation error from the API", async () => {
    const fetchMock = installFetch();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(CANONICAL))
      .mockResolvedValueOnce(jsonResponse({ detail: "obs.dt: must be at most 10 seconds" }, 422));

    const user = userEvent.setup();
    render(<ConfigBuilder />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate artifacts/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /generate artifacts/i }));

    await waitFor(() => {
      expect(screen.getByText(/obs\.dt: must be at most 10 seconds/i)).toBeInTheDocument();
    });
  });

  it("saves with an explicit artifact directory and overwrite opt-in", async () => {
    const fetchMock = installFetch();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(CANONICAL))
      .mockResolvedValueOnce(jsonResponse(PREVIEW_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          ...PREVIEW_RESPONSE,
          saved: true,
          written_paths: ["/srv/artifacts/run_emri_c_semicoherent.py", "/srv/artifacts/run_emri_c_semicoherent.pbs"],
        }),
      );

    const user = userEvent.setup();
    render(<ConfigBuilder />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate artifacts/i })).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: /generate artifacts/i }));
    await waitFor(() => {
      expect(screen.getByText(/#!\/usr\/bin\/env python3/)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/artifact directory/i), "/srv/artifacts");
    await user.click(screen.getByRole("button", { name: /save to server path/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved 2 artifact/i)).toBeInTheDocument();
    });
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/configs/save");
    expect(JSON.parse(init.body as string)).toEqual({
      config: expect.objectContaining({ out: "" }),
      artifact_dir: "/srv/artifacts",
      overwrite: false,
    });
  });
});

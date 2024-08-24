import json


def write_to_json(datafile_in: str, datafile_out: str, ceprot_datafile=""):
    results = []
    ceprot_inputs = []
    if ceprot_datafile:
        with open(ceprot_datafile) as f:
            ceprot_inputs = json.load(f)

    with open(f"{datafile_in}.output") as f:
        pred_lines = f.readlines()
    with open(f"{datafile_in}.gold") as f:
        ref_lines = f.readlines()

    if len(pred_lines) != len(ref_lines):
        raise ValueError("Number of predictions and references do not match")
    else:
        for i in range(len(pred_lines)):
            item = {"id": i}
            if ceprot_inputs:
                item["original"] = ceprot_inputs[i]["test_src"]
            item["prediction"] = pred_lines[i].strip()
            item["reference"] = ref_lines[i].strip()
            results.append(item)

    with open(datafile_out, "w") as fo:
        json.dump(results, fo, indent=4)
    print(f"Finish writing {len(results)} items from {datafile_in} to {datafile_out}")


if __name__ == "__main__":
    ceprot_datafile = "../../dataset/ceprot/test_new.json"
    datafile_in1 = "test_new/test_epoch0"
    datafile_out1 = "test_ceprot.json"
    write_to_json(datafile_in1, datafile_out1, ceprot_datafile)

    # datafile_in2 = "test_full/test_epoch1"
    # datafile_out2 = "test.json"
    # write_to_json(datafile_in2, datafile_out2)

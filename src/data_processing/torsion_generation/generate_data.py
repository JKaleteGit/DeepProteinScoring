'''
generate_data.py
Updated: 3/29/18

This script is used to generate torsion angle matricies used for convolutional
neural network training. The script will store representations in npz files
within a /torsion_data/ subdirectory.This script is used specifically to
generate data used for CASP experiments.

'''
import os
import numpy as np
from mpi4py import MPI
from scipy.ndimage.filters import gaussian_filter

# Data generation parameters
data_folder = '../../../data/Test/'
diheral_bin_count = 19

################################################################################

# Static Parameters
chain = 'A' # Chain Id might need to be changed for PDBs missing identifier
seed = 458762 # For random distribution of tasks using MPI
residues = ['ALA', 'ARG', 'ASN', 'ASP', 'ASX', 'CYS', 'GLN',
            'GLU', 'GLX', 'GLY', 'HIS', 'ILE', 'LEU', 'LYS',
            'MET', 'PHE', 'PRO', 'SER', 'THR', 'TRP', 'TYR',
            'UNK', 'VAL']

def parse_pdb(path, chain):
    '''
    Method parses atomic coordinate data from PDB.

    Params:
        path - str; PDB file path
        chain - str; chain identifier

    Returns:
        data - np.array; PDB data

    '''
    # Parse residue, atom type and atomic coordinates
    data = []
    with open(path, 'r') as f:
        lines = f.readlines()
        residue = None
        residue_data = []
        flag = False
        for row in lines:
            if row[:4] == 'ATOM' and row[21] == chain:
                flag = True
                if residue != row[17:20]:
                    data.append(residue_data)
                    residue_data = []
                    residue = row[17:20]
                atom_data = [row[17:20], row[12:16].strip(), row[30:38], row[38:46], row[47:54]]
                residue_data.append(atom_data)
            if row[:3] == 'TER' and flag: break
    data = np.array(data[1:])

    return data

def dihedral_angle(points):
    '''
    Method calculates dihedral angle for list of four points.

    Params:
        points - array; four atom x,y,z coordinates

    Returns:
        degree - float; dihedral angle in degrees

    '''
    # Parse points
    p0 = points[0]
    p1 = points[1]
    p2 = points[2]
    p3 = points[3]

    # normalize b1 so that it does not influence magnitude of vector
    # rejections that come next
    b0 = -1.0*(p1 - p0)
    b1 = p2 - p1
    b2 = p3 - p2
    b1 /= np.linalg.norm(b1)

    # vector rejections
    # v = projection of b0 onto plane perpendicular to b1
    #   = b0 minus component that aligns with b1
    # w = projection of b2 onto plane perpendicular to b1
    #   = b2 minus component that aligns with b1
    v = b0 - np.dot(b0, b1)*b1
    w = b2 - np.dot(b2, b1)*b1

    # angle between v and w in a plane is the torsion angle
    # v and w may not be normalized but that's fine since tan is y/x
    x = np.dot(v, w)
    y = np.dot(np.cross(b1, v), w)
    degree = np.degrees(np.arctan2(y, x))

    return degree

def calculate_dihedral_angles(protein_data):
    '''
    Method calculates dihedral angles for all amino acids in a given
    protein chain.

    Params:
        protein_data - np.array;

    Returns:
        dihedral_angles - np.array; Phi and Psi angles per residue

    '''
    # Calculate dihedral angles phi and psi for each amino acid in chain
    dihedral_angles = []
    for i in range(1, len(protein_data)-1):

        # Get atom coordinates for phi and psi angles
        amino_0 = np.array(protein_data[i-1])
        c_0 = amino_0[np.where(amino_0[:,1] == 'C')][:,2:]
        amino_1 = np.array(protein_data[i])
        n_1 = amino_1[np.where(amino_1[:,1] == 'N')][:,2:]
        ca_1 = amino_1[np.where(amino_1[:,1] == 'CA')][:,2:]
        c_1 = amino_1[np.where(amino_1[:,1] == 'C')][:,2:]
        amino_2 = np.array(protein_data[i+1])
        n_2 = amino_2[np.where(amino_2[:,1] == 'N')][:,2:]
        phi_atoms = np.concatenate([c_0,n_1,ca_1,c_1],axis=0)
        psi_atoms = np.concatenate([n_1,ca_1,c_1,n_2],axis=0)

        # Calculate dihedral angle phi and psi
        phi = dihedral_angle(phi_atoms.astype('float'))
        psi = dihedral_angle(psi_atoms.astype('float'))
        dihedral_angles.append([amino_1[0,0], phi, psi])

    dihedral_angles = np.array(dihedral_angles)

    return dihedral_angles

def bin_dihedral_angles(protein_data, diheral_bin_count):
    '''
    Method bins dihedral angles into 2D data grids for each type of
    amino acid type.

    Params:
        protein_data - np.array;
        diheral_bin_count - int; number of bins to bin dihedral angles

    Returns:
        binned_dihedral_angles - np.array; final data grid of binned dihedral
                                 angles per residue type.
                                 Shape - (bin_count, bin_count, 23)

    '''
    # Calculate dihedral angles
    dihedral_angles = calculate_dihedral_angles(protein_data)

    # Bin dihedral angles for each residue type
    binned_dihedral_angles = []
    for res in residues:

        # Get phi and psi Angles for specific residue type
        i = np.where(dihedral_angles[:,0] == res)
        phi_angles = dihedral_angles[i,1].astype('float')[0]
        psi_angles = dihedral_angles[i,2].astype('float')[0]

        # Bin angles in 2D histogram
        x_bins = np.linspace(-180, 180, num=diheral_bin_count+1)
        y_bins = np.linspace(-180, 180, num=diheral_bin_count+1)
        H, x_bins, y_bins = np.histogram2d(psi_angles, phi_angles,
                                                bins=(x_bins, y_bins))
        H = gaussian_filter(H, 0.5)
        binned_dihedral_angles.append(H)

    # Channels last transpose
    binned_dihedral_angles = np.array(binned_dihedral_angles)
    binned_dihedral_angles = np.transpose(binned_dihedral_angles, (1, 2, 0))

    return binned_dihedral_angles

if __name__ == '__main__':

    # Set paths relative to this file
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # MPI init
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    cores = comm.Get_size()

    # MPI task distribution
    if rank == 0:
        tasks = []

        if not os.path.exists(data_folder+'torsion_data'): os.mkdir(data_folder+'torsion_data')

        # Search for data directories
        for data_path in sorted(os.listdir(data_folder+'pdbs')):
            if data_path.endswith('.pdb'):
                tasks.append(data_folder+'pdbs/'+data_path)

        # Shuffle for random distribution
        np.random.seed(seed)
        np.random.shuffle(tasks)

    else: tasks = None

    # Broadcast tasks to all nodes and select tasks according to rank
    tasks = comm.bcast(tasks, root=0)
    tasks = np.array_split(tasks, cores)[rank]

    for t in tasks:
        path = t
        save_path = '/'.join(t.split('/')[:-2]) + '/torsion_data/'+ t.split('/')[-1][:-3]+'npz'

        # Parse PDB
        protein_data = parse_pdb(path, chain)

        try:
            # Bin diheral angles
            binned_dihedral_angles = bin_dihedral_angles(protein_data, diheral_bin_count)

            # Save data
            np.savez(save_path, binned_dihedral_angles)

            print("Generated:", '/'.join(save_path.split('/')[-3:]))

        except: print("Error generating data...")

    print("Data Generation Complete.")
